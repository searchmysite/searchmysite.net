from re import S
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app, jsonify
)
from werkzeug.exceptions import abort
from werkzeug.security import generate_password_hash
import psycopg2.extras
from os import environ
from searchmysite.admin.auth import login_required, set_login_session, do_indieauth_login, do_indieauth_login2
from searchmysite.db import get_db
from searchmysite.util import extract_domain, generate_validation_key, check_for_validation_key, get_host
import requests
import stripe

bp = Blueprint('add', __name__)


# SQL

sql_select_tiers = "SELECT tier, tier_name, default_full_reindex_frequency, default_part_reindex_frequency, default_indexing_page_limit, default_on_demand_reindexing, default_api_enabled, cost_amount, cost_currency, listing_duration "\
    "FROM tblTiers;"

# Selects the status of the highest listed tier (whether active or not)
sql_select_status = "SELECT l.status, l.tier, l.pending_state, d.moderator_approved, d.moderator_action_reason, d.indexing_enabled, d.indexing_disabled_reason, d.home_page, d.login_type, d.category FROM tblDomains d "\
    "INNER JOIN tblListingStatus l ON d.domain = l.domain "\
    "WHERE d.domain = (%s) "\
    "ORDER BY l.tier DESC;"

sql_insert_domain = "INSERT INTO tblDomains "\
    "(domain, home_page, domain_first_submitted, category, include_in_public_search, indexing_type) "\
    "VALUES ((%s), (%s), NOW(), (%s), TRUE, 'spider/default');"

sql_insert_basic_listing = "INSERT INTO tblListingStatus (domain, tier, status, status_changed, pending_state, pending_state_changed) "\
    "VALUES ((%s), (%s), 'PENDING', NOW(), 'MODERATOR_REVIEW', NOW());"

sql_insert_freefull_listing = "INSERT INTO tblListingStatus (domain, tier, status, status_changed, pending_state, pending_state_changed) "\
    "VALUES ((%s), (%s), 'PENDING', NOW(), 'LOGIN_AND_VALIDATION_METHOD', NOW());"

sql_update_freefull_step1 = "UPDATE tblDomains "\
    "SET include_in_public_search = (%s), login_type = (%s) WHERE domain = (%s);"\
    "UPDATE tblListingStatus "\
    "SET pending_state = (%s), pending_state_changed = NOW() "\
    "WHERE domain = (%s) AND tier = (%s);"

sql_update_freefull_step2 = "UPDATE tblDomains "\
    "SET email = (%s), password = (%s) WHERE domain = (%s);"\
    "UPDATE tblListingStatus "\
    "SET pending_state = (%s), pending_state_changed = NOW() "\
    "WHERE domain = (%s) AND tier = (%s);"\
    "INSERT INTO tblValidations "\
    "(domain, validation_method, validation_key) "\
    "VALUES ((%s), (%s), (%s));"

sql_update_freefull_step3 = "UPDATE tblListingStatus "\
    "SET pending_state = 'PAYMENT', pending_state_changed = NOW() "\
    "WHERE domain = (%s) AND tier = (%s);"

sql_update_freefull_validated = "UPDATE tblValidations "\
    "SET validation_success = TRUE, validation_date = NOW() "\
    "WHERE domain = (%s);"

# The SELECT coalesce(MAX(subscription_end),NOW()) AS subscription_end FROM tblSubscriptions WHERE domain = (%s) AND subscription_end > NOW()
# returns the latest subscription end date, if the subscription end date is in the future, or NOW() if none is set, so that subscriptions can be "stacked"
sql_insert_full_subscription = "INSERT INTO tblSubscriptions (domain, tier, subscribed, subscription_start, subscription_end, payment) "\
    "VALUES ((%s), (%s), NOW(), "\
        "(SELECT coalesce(MAX(subscription_end),NOW()) AS subscription_end FROM tblSubscriptions WHERE domain = (%s) AND subscription_end > NOW()), "\
        "(SELECT coalesce(MAX(subscription_end),NOW()) AS subscription_end FROM tblSubscriptions WHERE domain = (%s) AND subscription_end > NOW()) + (SELECT listing_duration FROM tblTiers WHERE tier = (%s)), "\
        "(SELECT cost_amount FROM tblTiers WHERE tier = (%s)));"

sql_update_full_listing_startandend = "UPDATE tblListingStatus "\
    "SET listing_start = NOW(), "\
        "listing_end = (SELECT MAX(subscription_end) FROM tblSubscriptions WHERE domain = (%s)) "\
    "WHERE domain = (%s) AND tier = (%s);"

sql_update_free_listing_startandend = "UPDATE tblListingStatus "\
    "SET listing_start = NOW(), "\
        "listing_end = NOW() + (SELECT listing_duration FROM tblTiers WHERE tier = (%s)) "\
    "WHERE domain = (%s) AND tier = (%s);"

sql_update_freefull_approved = "UPDATE tblListingStatus "\
    "SET status = 'ACTIVE', status_changed = NOW(), pending_state = NULL, pending_state_changed = NOW() "\
    "WHERE domain = (%s) AND tier = (%s); "\
    "UPDATE tblDomains SET "\
    "full_reindex_frequency = tblTiers.default_full_reindex_frequency, "\
    "part_reindex_frequency = tblTiers.default_part_reindex_frequency, "\
    "indexing_page_limit = tblTiers.default_indexing_page_limit, "\
    "on_demand_reindexing = tblTiers.default_on_demand_reindexing, "\
    "api_enabled = tblTiers.default_api_enabled, "\
    "indexing_enabled = TRUE, "\
    "full_indexing_status = 'PENDING', "\
    "full_indexing_status_changed = NOW() "\
    "FROM tblTiers WHERE tblTiers.tier = (%s) and tblDomains.domain = (%s);"

sql_select_validation_key = "SELECT validation_key FROM tblValidations WHERE domain = (%s);"


# Setup routes

@bp.route('/add/', methods=('GET', 'POST'))
def add():
    tiers = get_tier_data()
    if request.method == 'GET':
        return render_template('admin/add.html', tiers=tiers)
    else: # i.e. if POST 
        # Get user entered data
        home_page = request.form.get('home_page')
        site_category = request.form.get('site_category')
        tier = request.form.get('tier')
        if tier: tier = int(tier)
        # Get calculated data
        domain = extract_domain(home_page)
        if home_page.endswith(domain):
            home_page = home_page + '/'
        # Check if home page has been submitted already and if so what its status is
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_select_status, (domain,))
        result = cursor.fetchone()
        # Route to the next stage of the Add Site workflow
        if not home_page or not site_category or not tier: # There is client-side validation so this shouldn't be possible
            message = 'Please enter the required fields.'
            flash(message)
            return render_template('admin/add.html', tiers=tiers)
        elif not result: # Domain hasn't previously been submitted
            cursor.execute(sql_insert_domain, (domain, home_page, site_category))
            conn.commit()
            if tier == 1:
                cursor.execute(sql_insert_basic_listing, (domain, tier))
                conn.commit()
                return render_template('admin/add-success.html', tier=tier)
            elif tier == 2 or tier == 3:
                start_freefull_approval_session(domain, home_page, tier)
                return redirect(url_for('add.step1'))
        elif result['status'] == 'ACTIVE': # Domain already has an active listing
            if tier == result['tier']: # The user selected the same tier as the currently active tier
                message = 'The domain {} already has an active listing at the tier you selected with a home page at {}. If you would like to upgrade the listing please resubmit with a higher tier.'.format(domain, result['home_page'])
                flash(message)
                return redirect(url_for('add.add'))
            elif tier > result['tier']: # The user has selected to upgrade the tier 
                start_freefull_approval_session(domain, home_page, tier)
                return redirect(url_for('add.step1'))
        elif result['moderator_approved'] == False or result['indexing_enabled'] == False: # Rejected or indexing disabled
            if result['moderator_approved'] == False:
                message = 'Domain {} has previously been submitted but rejected for the following reason: {}. '.format(domain, result['moderator_action_reason'])
            if result['indexing_enabled'] == False:
                message = 'Domain {} has had indexing disabled for the following reason: {}. '.format(domain, result['indexing_disabled_reason'])
            message += 'Please use the Contact link if you would like to query this.'
            flash(message)
            return redirect(url_for('add.add'))
        elif result['status'] == 'PENDING':
            if result['tier'] == 1 and result['pending_state'] == 'MODERATOR_REVIEW':
                message = 'Domain {} is currently pending moderator review.'.format(domain)
                flash(message)
                return redirect(url_for('add.add'))
            elif result['tier'] == 2 or result['tier'] == 3:
                if result['pending_state'] == 'LOGIN_AND_VALIDATION_METHOD':
                    return redirect(url_for('add.step1'))
                elif result['pending_state'] == 'EMAIL' or result['pending_state'] == 'EMAIL_AND_PASSWORD':
                    return redirect(url_for('add.step2'))
                elif result['pending_state'] == 'INDIEAUTH_LOGIN' or result['pending_state'] == 'VALIDATION_CHECK':
                    return redirect(url_for('add.step3'))
                elif result['pending_state'] == 'PAYMENT':
                    return redirect(url_for('add.step4'))
            else:
                message = 'Unknown state'
                flash(message)
                current_app.logger.warn('Unknown PENDING state for {}.'.format(domain))
                return redirect(url_for('add.add'))
        # This shouldn't happen, but just in case
        else:
            message = 'Unknown status'
            flash(message)
            current_app.logger.warn('Unknown status for {}.'.format(domain))
            return redirect(url_for('add.add'))

@bp.route('/add/step1/', methods=('GET', 'POST'))
def step1():
    (home_page, domain, tier, login_type, site_category) = get_session_data()
    if not home_page: # i.e. redirect to /admin/add/ if someone has accessed /admin/add/step1/ outside the Add Site workflow session
        return redirect(url_for('add.add'))
    else:
        if request.method == 'GET':
            return render_template('admin/add-step1.html', tier=tier)
        else:
            include_public = request.form.get('include_public')
            if include_public == "False": include_public = False
            else: include_public = True 
            login_type = request.form.get('login_type')
            if login_type == 'PASSWORD': pending_state = 'EMAIL_AND_PASSWORD'
            else: pending_state = 'EMAIL' # i.e. login_type == 'INDIEAUTH'
            conn = get_db()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute(sql_update_freefull_step1, (include_public, login_type, domain, pending_state, domain, tier))
            conn.commit()
            return redirect(url_for('add.step2'))

@bp.route('/add/step2/', methods=('GET', 'POST'))
def step2():
    (home_page, domain, tier, login_type, site_category) = get_session_data()
    if not home_page:
        return redirect(url_for('add.add'))
    else:
        if request.method == 'GET':
            return render_template('admin/add-step2-email.html', tier=tier, login_type=login_type)
        else:
            # Get newly entered data from form
            email = request.form.get('email')
            # Get new data
            if login_type == 'PASSWORD':
                pending_state = 'VALIDATION_CHECK'
                validation_method = 'DCV'
                validation_key = generate_validation_key(42)
                password = generate_password_hash(request.form.get('password'))
            else:
                pending_state = 'INDIEAUTH_LOGIN' # i.e. login_type == 'INDIEAUTH'
                validation_method = 'INDIEAUTH'
                validation_key = None
                password = None
            if not email: # Note that there is client-side validation so this shouldn't be possible
                error_message = 'Please enter the required fields'
                flash(error_message)
                return render_template('admin/add-step2-email.html', tier=tier, login_type=login_type) # i.e. errors, so try again
            else:
                conn = get_db()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(sql_update_freefull_step2, (email, password, domain, pending_state, domain, tier, domain, validation_method, validation_key))
                conn.commit()
                return redirect(url_for('add.step3'))

@bp.route('/add/step3/', methods=('GET', 'POST'))
def step3():
    (home_page, domain, tier, login_type, site_category) = get_session_data()
    if not home_page:
        return redirect(url_for('add.add'))
    else:
        if login_type == 'PASSWORD':
            conn = get_db()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute(sql_select_validation_key, (domain,))
            result = cursor.fetchone()
            validation_key = result['validation_key']
            if request.method == 'GET':
                return render_template('admin/add-step3-validate.html', domain=domain, tier=tier, login_type=login_type, validation_key=validation_key)
            else:
                prefix = 'searchmysite-verification'
                validation_method = check_for_validation_key(domain, prefix, validation_key)
                if validation_method == 'DCV': # i.e. if the validation is successful
                    cursor.execute(sql_update_freefull_validated, (domain,))
                    conn.commit()
                    if current_app.config['ENABLE_PAYMENT'] == True and tier == 3:
                        cursor.execute(sql_update_freefull_step3, (domain, tier))
                        conn.commit()
                        return redirect(url_for('add.step4'))
                    else:
                        return redirect(url_for('add.success'))
                else:
                    message = 'Failed validation!'
                    flash(message)
                    return render_template('admin/add-step3-validate.html', domain=domain, tier=tier, login_type=login_type, validation_key=validation_key)
        elif login_type == 'INDIEAUTH':
            current_app.logger.info('Starting IndieAuth')
            if request.method == 'GET':
                if not request.args.get('redirect_uri') and not session.get('redirect_uri') and not request.args.get('client_id') and not session.get('client_id'):
                    host = get_host(request.host_url, request.headers)
                    redirect_uri = host[:-1] + url_for('add.step3') # assumes host ends with a trailing /
                    session['redirect_uri'] = redirect_uri
                    client_id = host
                    session['client_id'] = client_id
                    state = generate_validation_key(12)
                    current_app.logger.info('Setting redirect_uri = {}, client_id = {}, state = {}'.format(redirect_uri, client_id, state))
                    return render_template('admin/add-step3-validate.html', domain=domain, tier=tier, login_type=login_type, redirect_uri=redirect_uri, client_id=client_id, state=state)
                else:
                    code = request.args.get('code')
                    redirect_uri = session.get('redirect_uri')
                    client_id = session.get('client_id')
                    current_app.logger.info('Getting redirect_uri = {}, client_id = {}, code = {}'.format(redirect_uri, client_id, code))
                    indieauth = "https://indielogin.com/auth"
                    headers = {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8', 'Accept': 'application/json'}
                    payload = {'code': code, 'redirect_uri': redirect_uri, 'client_id': client_id}
                    response = requests.post(indieauth, data=payload, headers=headers)
                    responsejson = response.json()
                    if response.status_code != 200:
                        error = responsejson['error']
                        error_description = responsejson['error_description']
                        message = 'Unable to authenticate with IndieAuth: {} {}'.format(error, error_description)
                        flash(message)
                        return render_template('admin/add-step3-validate.html', domain=domain, tier=tier, login_type=login_type)
                    else: # Validated
                        conn = get_db()
                        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                        cursor.execute(sql_update_freefull_validated, (domain,))
                        conn.commit()
                        if current_app.config['ENABLE_PAYMENT'] == True and tier == 3:
                            cursor.execute(sql_update_freefull_step3, (domain, tier))
                            conn.commit()
                            return redirect(url_for('add.step4'))
                        else:
                            return redirect(url_for('add.success'))

@bp.route('/add/step4/', methods=('GET', 'POST'))
def step4():
    (home_page, domain, tier, login_type, site_category) = get_session_data()
    if not home_page:
        return redirect(url_for('add.add'))
    else:
        if request.method == 'GET':
            return render_template('admin/add-step4-payment.html', tier=tier, login_type=login_type)
        else:
            return render_template('admin/add-step4-payment.html', tier=tier, login_type=login_type)

@bp.route('/add/success/')
def success():
    (home_page, domain, tier, login_type, site_category) = get_session_data()
    if not home_page:
        return redirect(url_for('add.add'))
    else:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if tier == 2:
            cursor.execute(sql_update_free_listing_startandend, (tier, domain, tier))
        if tier == 3:
            cursor.execute(sql_insert_full_subscription, (domain, tier, domain, domain, tier, tier))
            cursor.execute(sql_update_full_listing_startandend, (domain, domain, tier))
        if tier == 2 or tier == 3:
            cursor.execute(sql_update_freefull_approved, (domain, tier, tier, domain))
        conn.commit()
    return render_template('admin/add-success.html', tier=tier, login_type=login_type)


## Payment routes

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


# Utilities

# Fields in tblTiers:
# tier_no, tier_name, 
# default_full_reindex_frequency, default_part_reindex_frequency, default_indexing_page_limit, default_on_demand_reindexing, default_api_enabled, 
# cost_amount, cost_currency, listing_duration
def get_tier_data():
    tiers = []
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_select_tiers)
    results = cursor.fetchall()
    if results:
        for result in results:
            tier = {}
            # tier_no
            tier['tier'] = result['tier']
            # tier_name
            tier['tier_name'] = result['tier_name']
            # full_reindex_frequency
            full_reindex_frequency = 'Every ' + str(result['default_full_reindex_frequency'])
            if full_reindex_frequency.endswith(', 0:00:00'): # Only tidies whole days for now, half days would end ', 12:00:00'
                full_reindex_frequency = full_reindex_frequency.replace(', 0:00:00', '')
            tier['full_reindex_frequency'] = full_reindex_frequency 
            # indexing_page_limit
            indexing_page_limit = str(result['default_indexing_page_limit']) + ' pages'
            tier['indexing_page_limit'] = indexing_page_limit
            # on_demand_reindexing
            on_demand_reindexing = 'Yes' if result['default_on_demand_reindexing'] == True else 'No'
            tier['on_demand_reindexing'] = on_demand_reindexing
            # api_enabled
            api_enabled = 'Yes' if result['default_api_enabled'] == True else 'No'
            tier['api_enabled'] = api_enabled
            # access_to_manage is implied and not explicitly in database
            access_to_manage = 'Yes' if int(result['tier']) > 1 else 'No'
            tier['access_to_manage'] = access_to_manage
            # cost
            if int(result['cost_amount']) == 0:
                cost = 'Free'
            else:
                cost = str(result['cost_currency']) + str(result['cost_amount'])
            tier['cost'] = cost
            # duration
            if int(result['tier']) > 1:
                listing_duration = str(result['listing_duration'])
                if listing_duration.endswith(', 0:00:00'): # Only tidies whole days for now, half days would end ', 12:00:00'
                    listing_duration = listing_duration.replace(', 0:00:00', '')
                tier['duration'] = listing_duration
            tiers.append(tier)
    return tiers

# Get previously entered data, using home page in session
def get_session_data():
    home_page = session.get('home_page')
    domain = extract_domain(home_page)
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_select_status, (domain,))
    result = cursor.fetchone()
    if result:
        tier = result['tier']
        login_type = result['login_type']
        site_category = result['category']
    else:
        home_page = None
        tier = None
        login_type = None
        site_category = None
    return (home_page, domain, tier, login_type, site_category)

def start_freefull_approval_session(domain, home_page, tier):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_insert_freefull_listing, (domain, tier))
    conn.commit()
    session.clear()
    session['home_page'] = home_page # Setting session with home_page rather than domain so they're not the same as a fully logged on user
    return







## OLD CODE



sql_select = "SELECT home_page, contact_email, site_category, owner_verified, validation_method, validation_key, moderator_approved, moderator_action_reason, indexing_enabled, indexing_disabled_reason, password "\
    "FROM tblDomains WHERE domain = (%s);"

# Quick Add
# Quick Add insert SQL below, moderator (admin) approve and reject SQL in admin.py

sql_quick_add = "INSERT INTO tblDomains "\
    "(domain, home_page, site_category, date_domain_added, api_enabled, owner_verified, validation_method, indexing_enabled, indexing_type, include_in_public_search) "\
    "VALUES ((%s), (%s), (%s), now(), FALSE, FALSE, 'QuickAdd', FALSE, 'spider/default', TRUE);"

# Verified Add steps
# Step 1: Create the new domain in tblDomains, with owner_verified=FALSE and validation_method='IndieAuth' or 'DCV'
#         (note also moderator_approved=TRUE and indexing_enabled=FALSE).
# Step 2: Add the email and site_category, and if DCV also add validation_key and password.
# Step 3: Set owner_verified=TRUE, and validation_date and expire_date
# (check if ENABLE_PAYMENT=TRUE and if so action accordingly)
# Step 4: Set the new verified indexing_frequency etc., mark as ready for indexing, and of course set 
#         indexing_enabled=TRUE
# Note:
# Some Verified Add submissions may already be being indexed via a Quick Add. If this is the case, they will
# skip step 1 which sets indexing_enabled to FALSE, and so continue to be indexed right through the verification 
# process. However, they will only get the main benefits of verification (increased page limit etc.) after the
# check for ENABLE_PAYMENT.

sql_indieauthanddcv_step1_insert = "INSERT INTO tblDomains "\
    "(domain, home_page, owner_verified, moderator_approved, validation_method, date_domain_added, indexing_enabled, indexing_type, include_in_public_search) "\
    "VALUES ((%s), (%s), FALSE, TRUE, (%s), now(), FALSE, 'spider/default', TRUE);"

sql_indieauth_step2_update = "UPDATE tblDomains "\
    "SET contact_email = (%s), site_category = (%s) "\
    "WHERE domain = (%s);"

sql_dcv_step2_update = "UPDATE tblDomains "\
    "SET contact_email = (%s), site_category = (%s), validation_key = (%s), password = (%s) "\
    "WHERE domain = (%s); "

sql_indieauthanddcv_step3_validate = "UPDATE tblDomains SET "\
    "owner_verified = TRUE, validation_date = now() "\
    "WHERE domain = (%s);"

sql_indieauthanddcv_step4_enableindexing = "UPDATE tblDomains SET "\
    "expire_date = now() + '1 year', api_enabled = TRUE, indexing_frequency = '3.5 days', indexing_page_limit = 500, "\
    "indexing_enabled = TRUE, indexing_current_status = 'PENDING', indexing_status_last_updated = now() "\
    "WHERE domain = (%s);"


@bp.route('/add/quick/', methods=('GET', 'POST'))
def quick():
    tiers = get_tier_data()
    if request.method == 'GET':
        return render_template('admin/add-quick.html', tiers=tiers)
    else: # i.e. if POST 
        home_page = request.form.get('home_page')
        site_category = request.form.get('site_category')
        domain = extract_domain(home_page)
        if home_page.endswith(domain):
            home_page = home_page + '/'
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        error_message = None
        cursor.execute(sql_select, (domain,))
        result = cursor.fetchone()
        # 8 routes:
        # 1. No home page entered (although this shouldn't happen because the front end has it as a required field)
        # 2. No site category entered
        # 3. Domain has been owner verified and is already being indexed - click on Manage Site and login if you are the owner
        # 4. Domain has not been owner verified but is already being indexed - click on Add via IndieAuth or Add via DCV if you want to verify
        # 5. Domain has been owner verified and but indexing has been disabled - show reason it has been disabled
        # 6. Domain has already been submitted (Quick Add) but is awaiting moderator approval - no further action
        # 7. Domain has previously been submitted but rejected - show rejection reason
        # 8. Domain is already present but not being indexed
        # Note:
        #    There are 2 scenarios which aren't explicitly picked up:
        #    1. Previously approved Quick Add sites which have had indexing disabled
        #    and
        #    2. Verified Add sites which haven't already had indexing enabled via Quick Add and which are awaiting verification
        #    this is because they have the same state, i.e.
        #    result['owner_verified'] == False and result['moderator_approved'] == True and result['indexing_enabled'] == False
        # Note also:
        #    It is possible to do a Quick Add and have a site indexed before a Verified Add, but not the other way around.
        #    See also comments in the Verified Add SQL section above.
        if not home_page:
            message = 'Home page is required.'
            flash(message)
            return render_template('admin/add-quick.html')
        if not site_category:
            message = 'Please specify the site category.'
            flash(message)
            return render_template('admin/add-quick.html')
        elif result is not None and result['owner_verified'] == True and result['moderator_approved'] == True and result['indexing_enabled'] == True:
            # i.e. verified add, moderator approved, and indexed
            message = 'Domain {} is already being indexed with a home page at {} - you can click on Manage Site if you are the owner.'.format(domain, result['home_page'])
            flash(message)
            return render_template('admin/add-quick.html')
        elif result is not None and result['owner_verified'] == False and result['moderator_approved'] == True and result['indexing_enabled'] == True:
            # i.e. quick add, moderator approved, and indexed
            message = 'Domain {} is already being indexed with a home page at {} - click on Verified Add if you are the owner and want to change from Quick Add to Verified Add.'.format(domain,result['home_page'])
            flash(message)
            return render_template('admin/add-quick.html')
        elif result is not None and result['owner_verified'] == True and result['moderator_approved'] == True and result['indexing_enabled'] == False:
            # i.e. verified add, moderator approved, but with indexing disabled
            message = 'Domain {} with a home page at {} has had indexing disabled for the following reason: {}. '.format(domain, result['home_page'], result['indexing_disabled_reason'])
            message += 'Please use the Contact link if you would like to query this.'
            flash(message)
            return render_template('admin/add-quick.html')
        elif result is not None and result['moderator_approved'] is None:
            # i.e. submitted and is pending moderator review
            message = 'Domain {} with a home page at {} has already been submitted and is pending moderator review.'.format(domain, result['home_page'])
            flash(message)
            return render_template('admin/add-quick.html')
        elif result is not None and result['moderator_approved'] == False:
            # i.e. previously submitted and rejected
            message = 'Domain {} with a home page at {} has previously been submitted but rejected for the following reason: {}. '.format(domain, result['home_page'], result['moderator_action_reason'])
            message += 'Please use the Contact link if you would like to query this.'
            flash(message)
            return render_template('admin/add-quick.html')
        elif result is not None and result['indexing_enabled'] == False:
            # i.e. not being indexed. Should effectively be a catchall because all the indexing_enabled=True and moderator_approved states should be covered
            message = 'Domain {} with a home page at {} has previously been submitted although is not being indexed. '.format(domain, result['home_page'])
            message += 'Please use the Contact link if you would like further information.'
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
    return_action, return_target = do_indieauth_login(current_page, next_page, addsite_workflow, sql_indieauthanddcv_step1_insert)
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
            cursor.execute(sql_indieauth_step2_update, (email, site_category, domain, ))
            cursor.execute(sql_indieauthanddcv_step3_validate, (domain, ))
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
        cursor.execute(sql_select, (domain, ))
        result = cursor.fetchone()
        owner_verified = result['owner_verified']
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
        cursor.execute(sql_select, (domain,))
        result = cursor.fetchone()
        error_message = None
        if not home_page:
            error_message = 'Home page is required.'
            flash(error_message)
            return render_template('admin/add-dcv1.html') # i.e. errors, so try again
        elif result is not None and result['owner_verified'] == True and result['indexing_enabled'] == True:
            # i.e. fully validated and owner_verified (existing but non owner_verified should pass through to next step)
            error_message = 'The home page at {} is already registered for domain {}.'.format(result['home_page'], domain)
            flash(error_message)
            return render_template('admin/add-dcv1.html')
        elif result is not None and result['contact_email'] is None and result['password'] is None: # i.e. submitted but on step 2
            session.clear()
            session['home_page'] = home_page
            return redirect(url_for('add.viadcv2')) 
        elif result is not None and result['contact_email'] is not None and result['password'] is not None and result['owner_verified'] == False:
            # i.e. submitted but on step 3
            # this is an important case for the people who have had to return to the Add Site at a later date
            # e.g. in cases where it has taken them some time to setup their validation_key
            session.clear()
            session['home_page'] = home_page
            return redirect(url_for('add.viadcv3')) 
        elif result is not None and result['owner_verified'] == True and current_app.config['ENABLE_PAYMENT']: # i.e. verified but not paid (if payment enabled)
            # this is another important case for people who have verified ownership but not paid the listing fee
            session.clear()
            session['home_page'] = home_page
            return redirect(url_for('add.viadcv4')) 
        else: # i.e. domain has not been submitted
            session.clear()
            session['home_page'] = home_page
            cursor.execute(sql_indieauthanddcv_step1_insert, (domain, home_page, 'DCV'))
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
            cursor.execute(sql_dcv_step2_update, (email, site_category, validation_key, generate_password_hash(password), domain, ))
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
        cursor.execute(sql_select, (domain, ))
        result = cursor.fetchone()
        validation_key = result['validation_key']
        owner_verified = result['owner_verified']
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
                cursor.execute(sql_indieauthanddcv_step3_validate, (domain, ))
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
        cursor.execute(sql_select, (domain, ))
        result = cursor.fetchone()
        validation_key = result['validation_key']
        owner_verified = result['owner_verified']
    if not home_page:
        return redirect(url_for('add.viadcv1'))
    else:
        if not validation_key:
            error_message = 'Not validated at this time. Please try again.'
            flash(error_message)
            return render_template('admin/add-dcv3.html', domain=domain, validation_key=validation_key) # try again
        else:
            return render_template('admin/add-payment.html', submission_method="usernamepassword")



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
        cursor.execute(sql_select, (domain, ))
        result = cursor.fetchone()
        #validation_method = result['validation_method']
        owner_verified = result['owner_verified']
        #site_category = result['site_category']
        #email = result['contact_email']
        #if validation_method == "DCV": method = "usernamepassword"
        #if validation_method == "IndieAuth": method = "indieauth"
        if owner_verified:
            cursor.execute(sql_indieauthanddcv_step4_enableindexing, (domain, ))
            conn.commit()
            #move_from_pending_to_indexed(domain, method, site_category, email)
            return render_template('admin/add-verifiedsuccess.html')
        else:
            return render_template('admin/success.html', title="Verified Add End Page", message="<p>You have reached the end of the Verified Add process.</p>")

@bp.route('/checkout/cancelled/')
def checkout_cancelled():
    return render_template('admin/checkout-cancelled.html')

#def move_from_pending_to_indexed(domain, validation_method, site_category, email):
#    conn = get_db()
#    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
#    if validation_method == "indieauth":
#        cursor.execute(sql_indieauth_finalstep, (email, site_category, domain, ))
#    elif validation_method == "usernamepassword":
#        cursor.execute(sql_dcv_finalstep, (domain, ))
#    conn.commit()
#    cursor.execute(sql_validated_update, (domain, ))
#    conn.commit()
#    set_login_session(domain, validation_method)
#    return


