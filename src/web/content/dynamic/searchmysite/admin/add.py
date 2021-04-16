from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app, jsonify
)
from werkzeug.exceptions import abort
from werkzeug.security import generate_password_hash
import psycopg2.extras
from os import environ
from searchmysite.admin.auth import login_required, set_login_session, do_indieauth_login
from searchmysite.db import get_db
from searchmysite.util import extract_domain, generate_validation_key, check_for_validation_key, get_host
import requests
import stripe

bp = Blueprint('add', __name__)

# SQL

sql_select_indexed = 'SELECT * FROM tblIndexedDomains WHERE domain = (%s);'

sql_select_pending = 'SELECT * FROM tblPendingDomains WHERE domain = (%s);'

sql_select_excluded = 'SELECT * FROM tblExcludeDomains WHERE domain = (%s);'

sql_indieauth_step1pending = "INSERT INTO tblPendingDomains "\
    "(domain, home_page, owner_submitted, submission_method, date_domain_added) "\
    "VALUES ((%s), (%s), TRUE, 'IndieAuth', now());"

sql_indieauth_step2email = "UPDATE tblPendingDomains "\
    "SET contact_email = (%s), site_category = (%s) "\
    "WHERE domain = (%s); "

# Stage 1: Create the new domain in tblIndexedDomains if it doesn't exist. It is important to handle cases where 
# it does exist (via ON CONFLICT) because a domain may have been submitted via Quick Add and then again later via Verified Add.
# Stage 2: Copy in the values for date_domain_added from tblPendingDomains.
# Note that owner_verified/owner_submitted and validation_method/submission_method are reset in case they were different from an earlier Quick Add. 
# If the domain was already in tblIndexedDomains, values from the Verified Add will take preference over any values from Quick Add
# (except for home_page).
# Stage 3: Update the email.
# Note: Then need to run sql_validated_update
sql_indieauth_finalstep = "INSERT INTO tblIndexedDomains (domain, home_page) "\
    "VALUES ((%s), (SELECT home_page from tblPendingDomains WHERE domain = (%s))) "\
    "ON CONFLICT (domain) DO NOTHING; "\
    "UPDATE tblIndexedDomains SET "\
    "date_domain_added = (SELECT date_domain_added from tblPendingDomains WHERE domain = (%s)), "\
    "owner_verified = TRUE, "\
    "validation_method = 'IndieAuth', "\
    "site_category = (%s) "\
    "WHERE domain = (%s); "\
    "UPDATE tblIndexedDomains SET contact_email = (%s) WHERE domain = (%s);"

sql_dcv_step1home = "INSERT INTO tblPendingDomains "\
    "(domain, home_page, owner_submitted, submission_method, date_domain_added) "\
    "VALUES ((%s), (%s), TRUE, 'DCV', now());"

sql_dcv_step2login = "UPDATE tblPendingDomains "\
    "SET site_category = (%s), contact_email = (%s), validation_key = (%s), password = (%s) "\
    "WHERE domain = (%s); "

sql_mark_as_validated = "UPDATE tblPendingDomains SET owner_verified = TRUE WHERE domain = (%s); "

# Comments as per for sql_indieauth_step2validated above, except:
# Stage 2 additionally updates contact_email, validation_key, password
# minus Stage 3: Update the email.
# Note: Then need to run sql_validated_update as well
sql_dcv_finalstep = "INSERT INTO tblIndexedDomains (domain, home_page) "\
    "VALUES ((%s), (SELECT home_page from tblPendingDomains WHERE domain = (%s))) "\
    "ON CONFLICT (domain) DO NOTHING; "\
    "UPDATE tblIndexedDomains SET "\
    "contact_email = (SELECT contact_email from tblPendingDomains WHERE domain = (%s)), "\
    "date_domain_added = (SELECT date_domain_added from tblPendingDomains WHERE domain = (%s)), "\
    "owner_verified = TRUE, "\
    "validation_key = (SELECT validation_key from tblPendingDomains WHERE domain = (%s)), "\
    "validation_method = 'DCV', "\
    "site_category = (SELECT site_category from tblPendingDomains WHERE domain = (%s)), "\
    "password = (SELECT password from tblPendingDomains WHERE domain = (%s)) "\
    "WHERE domain = (%s); "

sql_validated_update = "UPDATE tblIndexedDomains "\
    "SET expire_date = now() + '1 year', api_enabled = TRUE, validation_date = now(), "\
    "indexing_frequency = '3.5 days', indexing_page_limit = 500, indexing_current_status = 'PENDING', indexing_status_last_updated = now() "\
    "WHERE domain = (%s); "\
    "DELETE FROM tblPendingDomains WHERE domain = (%s);"

sql_quick_add = "INSERT INTO tblPendingDomains "\
    "(domain, home_page, owner_submitted, submission_method, site_category, date_domain_added) "\
    "VALUES ((%s), (%s), FALSE, 'QuickAdd', (%s), now());"

# Setup routes

@bp.route('/add/')
def add():
    return redirect(url_for('add.quick'))

@bp.route('/add/quick/', methods=('GET', 'POST'))
def quick():
    if request.method == 'GET':
        return render_template('admin/add-quick.html')
    else: # i.e. if POST 
        home_page = request.form.get('home_page')
        site_category = request.form.get('site_category')
        domain = extract_domain(home_page)
        if home_page.endswith(domain):
            home_page = home_page + '/'
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_select_indexed, (domain,))
        indexed_result = cursor.fetchone()
        cursor.execute(sql_select_pending, (domain,))
        pending_result = cursor.fetchone()
        cursor.execute(sql_select_excluded, (domain,))
        excluded_result = cursor.fetchone()
        error_message = None
        # 7 routes:
        # 1. No home page entered (although this shouldn't happen because the front end has it as a required field)
        # 2. No site category entered
        # 3. Domain is already being indexed and has been owner verified - click on Manage Site and login if you are the owner
        # 4. Domain is already being indexed but has not been owner verified - click on Add via IndieAuth or Add via DCV if you want to verify
        # 5. Domain has already been submitted but is awaiting review (if Quick Add) or verification (if Verified Add) - no further action 
        #    (note: if someone does Quick Add and is successfully reviewed they can have their site indexed before completing Verified Add,
        #    but if they go to Verified Add first but don't complete then they won't be able to complete Quick Add and therefore  
        #    won't be able to get any indexing - this could be handled by adding pending_result['submission_method'] == 'QuickAdd'
        #    and allowing other submission methods through, but the issue with this would be that sql_quick_add would set the 
        #    submission_method to 'QuickAdd' meaning they'd have to restart the Verified Add)
        # 6. Domain has previously been submitted but rejected - show rejection reason
        # 7. Domain has not already been submitted - submit for review
        if not home_page:
            message = 'Home page is required.'
            flash(message)
            return render_template('admin/add-quick.html')
        if not site_category:
            message = 'Please specify the site category.'
            flash(message)
            return render_template('admin/add-quick.html')
        elif indexed_result is not None and indexed_result['owner_verified'] == True: # i.e. indexed and fully validated by owner
            message = 'Domain {} is already being indexed with a home page at {} - you can click on Manage Site if you are the owner.'.format(domain, indexed_result['home_page'])
            flash(message)
            return render_template('admin/add-quick.html')
        elif indexed_result is not None and indexed_result['owner_verified'] == False: # i.e. indexed but not validated by owner
            message = 'Domain {} is already being indexed with a home page at {} - click on Verified Add if you are the owner and want to change from Quick Add to Verified Add.'.format(domain, indexed_result['home_page'])
            flash(message)
            return render_template('admin/add-quick.html')
        elif pending_result is not None: # i.e. not already indexed, but already submitted and pending review (if Quick Add) or verification (if Verified Add)
            message = 'Domain {} with a home page at {} has already been submitted and is pending review/verification.'.format(domain, pending_result['home_page'])
            flash(message)
            return render_template('admin/add-quick.html')
        elif excluded_result is not None: # i.e. previously submitted and rejected
            message = 'Domain {} with a home page at {} has previously been submitted but rejected for the following reason: {}. '.format(domain, excluded_result['home_page'], excluded_result['reason'])
            message += 'Please use the Contact link if you would like to query this.'
            flash(message)
            return render_template('admin/add-quick.html')
        else: # i.e. not already indexed and not already submitted
            cursor.execute(sql_quick_add, (domain, home_page, site_category))
            conn.commit()
            return redirect(url_for('add.quick_success'))

@bp.route('/add/indieauth/')
def indieauth():
    return render_template('admin/add-indieauth.html')

@bp.route('/add/dcv/')
def dcv():
    return render_template('admin/add-dcv.html')

@bp.route('/add/indieauth1home/')
def viaindieauth1():
    current_page = 'admin/add-indieauth1.html'
    next_page = url_for('add.viaindieauth2')
    addsite_workflow = True
    return_action, return_target = do_indieauth_login(current_page, next_page, addsite_workflow, sql_indieauth_step1pending)
    if (return_action == "render_template"):
        return render_template(return_target, redirect_uri=session['redirect_uri'], client_id=session['client_id'], state=session['state'])
    else:
        return redirect(return_target)

@bp.route('/add/indieauth2email/', methods=('GET', 'POST'))
def viaindieauth2():
    if request.method == 'GET':
        return render_template('admin/add-indieauth2.html')
    else: # i.e. if POST 
        home_page = session.get('home_page')
        domain = extract_domain(home_page)
        email = request.form.get('email')
        site_category = request.form.get('site_category')
        if not email:
            error_message = 'Email is required.'
            flash(error_message)
            return render_template('admin/add-indieauth2.html') # i.e. errors, so try again
        elif not site_category:
            error_message = 'Site category is required.'
            flash(error_message)
            return render_template('admin/add-indieauth2.html') # i.e. errors, so try again
        else:
            conn = get_db()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute(sql_indieauth_step2email, (email, site_category, domain, ))
            cursor.execute(sql_mark_as_validated, (domain, ))
            conn.commit()
            if current_app.config['ENABLE_PAYMENT'] == True:
                return redirect(url_for('add.viaindieauth3'))
            else:
                return redirect(url_for('add.verified_success'))

@bp.route('/add/indieauth3payment/', methods=('GET', 'POST'))
def viaindieauth3():
    home_page = session.get('home_page')
    domain = extract_domain(home_page)
    if home_page is not None:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_select_pending, (domain, ))
        pending_result = cursor.fetchone()
        owner_verified = pending_result['owner_verified']
    if not home_page:
        return redirect(url_for('add.viaindieauth1'))
    else:
        if not owner_verified:
            error_message = 'Not validated at this time. Please try again.'
            flash(error_message)
            return render_template('admin/add-indieauth2.html') # try again
        else:
            return render_template('admin/add-payment.html', submission_method="indieauth")

# 6 routes through DCV step 1:
# 1. No home page entered (although this shouldn't happen because the front end has it as a required field)
# 2. Domain has already been submitted and is fully validated
# 3. Domain has already been submitted, but still at step 2 Login Details
# 4. Domain has already been submitted, but still at step 3 Validate
# 5. Domain has already been submitted and validated, but (if payment is enabled) step 4 Payment has not been completed
# 6. Domain has not been submitted
# 
# Note the whole Domain Control Validation process can only be completed once per domain, given the domain is a primary key.
# So if the owner successfully validated <username>.github.io that would be saved in the database for the github.io domain, 
# meaning someone else would not be able to validate ownership of anoither site on the github.io domain. 
# The solution for this is to maintain a list of domains which allow subdomains via 
# tblSettings WHERE setting_name = 'domain_allowing_subdomains' which util.extract_domain references.
# Another potential solution would be to make the home page the primary key, but then it wouldn't be
# Domain Control Validation as and it would veer from the own your own content and cdomain concept.
#  
@bp.route('/add/dcv1home/', methods=('GET', 'POST'))
def viadcv1():
    if request.method == 'GET':
        return render_template('admin/add-dcv1.html')
    else: # i.e. if POST 
        home_page = request.form.get('home_page')
        domain = extract_domain(home_page)
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_select_indexed, (domain,))
        indexed_result = cursor.fetchone()
        cursor.execute(sql_select_pending, (domain,))
        pending_result = cursor.fetchone()
        error_message = None
        if not home_page:
            error_message = 'Home page is required.'
            flash(error_message)
            return render_template('admin/add-dcv1.html') # i.e. errors, so try again
        elif indexed_result is not None and indexed_result['owner_verified'] == True: # i.e. fully validated and owner_verified (existing but non owner_verified should pass through to next step)
            error_message = 'The home page at {} is already registered for domain {}.'.format(indexed_result['home_page'], domain)
            flash(error_message)
            return render_template('admin/add-dcv1.html')
        elif pending_result is not None and pending_result['contact_email'] is None and pending_result['password'] is None: # i.e. submitted but on step 2
            session.clear()
            session['home_page'] = home_page
            return redirect(url_for('add.viadcv2')) 
        elif pending_result is not None and pending_result['contact_email'] is not None and pending_result['password'] is not None and not pending_result['owner_verified']: # i.e. submitted but on step 3
            # this is an important case for the people who have had to return to the Add Site at a later date
            # e.g. in cases where it has taken them some time to setup their validation_key
            session.clear()
            session['home_page'] = home_page
            return redirect(url_for('add.viadcv3')) 
        elif pending_result is not None and pending_result['owner_verified'] and current_app.config['ENABLE_PAYMENT']: # i.e. verified but not paid (if payment enabled)
            # this is another important case for people who have verified ownership but not paid the listing fee
            session.clear()
            session['home_page'] = home_page
            return redirect(url_for('add.viadcv4')) 
        else: # i.e. domain has not been submitted
            session.clear()
            session['home_page'] = home_page
            cursor.execute(sql_dcv_step1home, (domain, home_page, ))
            conn.commit()
            return redirect(url_for('add.viadcv2')) # success, so move on to validate step

# Assuming people only get here via a redirect from step 1, and therefore that the data is in the state it should be for step 2
@bp.route('/add/dcv2login/', methods=('GET', 'POST'))
def viadcv2():
    home_page = session.get('home_page')
    domain = extract_domain(home_page)
    site_category = request.form.get('site_category')
    if request.method == 'GET':
        return render_template('admin/add-dcv2.html', domain=domain)
    else: # i.e. if POST 
        email = request.form['email']
        password = request.form['password']
        if not home_page:
            return redirect(url_for('add.viadcv1'))
        elif not email:
            error_message = 'Email is required.'
            flash(error_message)
            return render_template('admin/add-dcv2.html', domain=domain) # i.e. errors, so try again
        elif not password:
            error_message = 'Password is required.'
            flash(error_message)
            return render_template('admin/add-dcv2.html', domain=domain) # i.e. errors, so try again
        elif not site_category:
            error_message = 'Site category is required.'
            flash(error_message)
            return render_template('admin/add-dcv2.html', domain=domain) # i.e. errors, so try again
        else:
            conn = get_db()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            validation_key = generate_validation_key(42)
            cursor.execute(sql_dcv_step2login, (site_category, email, validation_key, generate_password_hash(password), domain, ))
            conn.commit()
            return redirect(url_for('add.viadcv3'))

# As per step 2, assuming people only get here via a redirect from step 1 or step 2
@bp.route('/add/dcv3validate/', methods=('GET', 'POST'))
def viadcv3():
    home_page = session.get('home_page')
    domain = extract_domain(home_page)
    validation_key = ""
    if home_page is not None:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_select_pending, (domain, ))
        pending_result = cursor.fetchone()
        validation_key = pending_result['validation_key']
        owner_verified = pending_result['owner_verified']
    if request.method == 'GET':
        return render_template('admin/add-dcv3.html', domain=domain, validation_key=validation_key)
    else: # i.e. if POST 
        if not home_page:
            return redirect(url_for('add.viadcv1'))
        elif not owner_verified:
            prefix = "searchmysite-verification"
            validation_method = check_for_validation_key(domain, prefix, validation_key)
            if not validation_method:
                error_message = 'Not validated at this time. Please try again.'
                flash(error_message)
                return render_template('admin/add-dcv3.html', domain=domain, validation_key=validation_key) # try again
            else:
                cursor.execute(sql_mark_as_validated, (domain, ))
                conn.commit()
                if current_app.config['ENABLE_PAYMENT'] == True:
                    return redirect(url_for('add.viadcv4'))
                else:
                    return redirect(url_for('add.verified_success'))
        else:
            if current_app.config['ENABLE_PAYMENT'] == True:
                return redirect(url_for('add.viadcv4'))
            else:
                return redirect(url_for('add.verified_success'))

@bp.route('/add/dcv4payment/')
def viadcv4():
    home_page = session.get('home_page')
    domain = extract_domain(home_page)
    if home_page is not None:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_select_pending, (domain, ))
        pending_result = cursor.fetchone()
        validation_key = pending_result['validation_key']
        owner_verified = pending_result['owner_verified']
    if not home_page:
        return redirect(url_for('add.viadcv1'))
    else:
        if not validation_key:
            error_message = 'Not validated at this time. Please try again.'
            flash(error_message)
            return render_template('admin/add-dcv3.html', domain=domain, validation_key=validation_key) # try again
        else:
            return render_template('admin/add-payment.html', submission_method="usernamepassword")

@bp.route('/checkout/config/', methods=['GET'])
def get_publishable_key():
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
    price = stripe.Price.retrieve(current_app.config['STRIPE_PRODUCT_ID'])
    stripe_config = {
        'publicKey': current_app.config['STRIPE_PUBLISHABLE_KEY'],
    }
    return jsonify(stripe_config)

@bp.route("/checkout/create-checkout-session/")
def create_checkout_session():
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
    domain_url = get_host(request.host_url, request.headers)
    domain_url = domain_url.rstrip('/')
    try:
        # Create new Checkout Session for the order
        # Other optional params include:
        # [billing_address_collection] - to display billing address details on the page
        # [customer] - if you have an existing Stripe Customer ID
        # [payment_intent_data] - capture the payment later
        # [customer_email] - prefill the email input in the form
        # For full details see https://stripe.com/docs/api/checkout/sessions/create
        # ?session_id={CHECKOUT_SESSION_ID} means the redirect will have the session ID set as a query param
        checkout_session = stripe.checkout.Session.create(
            success_url = domain_url + url_for('add.verified_success') + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url = domain_url + url_for('add.checkout_cancelled'),
            payment_method_types=["card"],
            mode="payment",
            line_items=[
                {
                    "price": current_app.config['STRIPE_PRODUCT_ID'],
                    "quantity": 1
                }
            ]
        )
        return jsonify({"sessionId": checkout_session["id"]})
    except Exception as e:
        return jsonify(error=str(e)), 403

@bp.route("/checkout/webhook/", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, current_app.config['STRIPE_ENDPOINT_SECRET']
        )
    except ValueError as e:
        # Invalid payload
        current_app.logger.error('Invalid payload.')
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        current_app.logger.error('Invalid signature.')
        return "Invalid signature", 400
    # Handle the checkout.session.completed event
    if event["type"] == "checkout.session.completed":
        current_app.logger.info('Payment was successful.')
    return "Success", 200

@bp.route('/add/quick/success/')
def quick_success():
    return render_template('admin/add-quicksuccess.html')

@bp.route('/add/success/')
def verified_success():
    home_page = session.get('home_page')
    domain = extract_domain(home_page)
    if home_page is not None:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_select_pending, (domain, ))
        pending_result = cursor.fetchone()
        submission_method = pending_result['submission_method']
        owner_verified = pending_result['owner_verified']
        site_category = pending_result['site_category']
        email = pending_result['contact_email']
        if submission_method == "DCV": method = "usernamepassword"
        if submission_method == "IndieAuth": method = "indieauth"
        if owner_verified:
            move_from_pending_to_indexed(domain, method, site_category, email)
            return render_template('admin/add-verifiedsuccess.html')
        else:
            return render_template('admin/success.html', title="Verified Add End Page", message="<p>You have reached the end of the Verified Add process.</p>")

@bp.route('/checkout/cancelled/')
def checkout_cancelled():
    return render_template('admin/checkout-cancelled.html')

def move_from_pending_to_indexed(domain, submission_method, site_category, email):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if submission_method == "indieauth":
        cursor.execute(sql_indieauth_finalstep, (domain, domain, domain, site_category, domain, email, domain, ))
    elif submission_method == "usernamepassword":
        cursor.execute(sql_dcv_finalstep, (domain, domain, domain, domain, domain, domain, domain, domain, ))
    conn.commit()
    cursor.execute(sql_validated_update, (domain, domain, ))
    conn.commit()
    set_login_session(domain, submission_method)
    return
