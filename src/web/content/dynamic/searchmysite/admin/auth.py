import functools
import psycopg2.extras
from os import environ
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app
)
from werkzeug.security import check_password_hash, generate_password_hash
from searchmysite.db import get_db
from searchmysite.util import generate_validation_key, extract_domain, send_email, get_host
import requests

sql_select = "SELECT l.status, l.tier, d.password, d.login_type FROM tblDomains d "\
    "INNER JOIN tblListingStatus l ON d.domain = l.domain "\
    "WHERE d.domain = (%s) "\
    "ORDER BY l.tier ASC;"
sql_select_admin = "SELECT * from tblPermissions WHERE role = 'admin' AND domain = (%s);"
sql_last_login_time = "UPDATE tblDomains SET last_login = now() WHERE domain = (%s);"
sql_change_password = "UPDATE tblDomains SET password = (%s) WHERE domain = (%s);"
sql_forgotten_password = "UPDATE tblDomains SET forgotten_password_key = (%s), forgotten_password_key_expiry = now() + '30 minutes' WHERE domain = (%s);"
sql_forgotten_password_login = "SELECT * FROM tblDomains WHERE forgotten_password_key = (%s) AND forgotten_password_key_expiry < now() + '30 minutes';"

bp = Blueprint('auth', __name__)


# This is normally reached by a redirect from login_required
# although you can also navigate direct to the login page.
#
# There are two login boxes, dealt with the two main parts to this code:
# 1. The username and password login box, dealt with via the POST section
# 2. The IndieAuth login box, dealt with via the GET section
@bp.route('/login/', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        domain = request.form['domain']
        password = request.form['password']
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        error = None
        cursor.execute(sql_select, (domain,))
        results = cursor.fetchone()
        if results is None:
            error = 'Incorrect domain. Are you registered?'
        elif not results['password'] or not results['login_type'] == 'PASSWORD': # correct domain but no password set, probably because they initially setup via IndieAuth
            error = 'Please use the Login with IndieAuth box.'
        elif not results['status'] == 'ACTIVE' and not (results['tier'] == 2 or results['tier'] == 3):
            error = 'You don\'t have an active Full or Free Trial subscription. Please subscribe.'
        elif not check_password_hash(results['password'], password):
            error = 'Incorrect password.'
        if error is None:
            set_login_session(domain, "usernamepassword")
            return redirect(url_for('manage.manage'))
        flash(error)
        return render_template('admin/login.html')
    else:
        current_page = 'admin/login.html'
        next_page = url_for('manage.manage')
        addsite_workflow = False
        insertdomainsql = None
        return_action, return_target = do_indieauth_login(current_page, next_page, addsite_workflow, insertdomainsql)
        if (return_action == "render_template"):
            return render_template(return_target, redirect_uri=session['redirect_uri'], client_id=session['client_id'], state=session['state'])
        else:
            return redirect(return_target)

@bp.route('/logout/')
def logout():
    session.clear()
    return render_template('admin/success.html', title="Logout Success", message="<p>You have successfully logged out.</p><p>You can continue to perform activities such as <a href=\"/\">search</a> or <a href=\"/search/browse/\">browse</a> without being logged in.</p>")

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if session.get('logged_in_domain') is None: # i.e. if not logged in
            param_state = request.args.get('state')
            code = request.args.get('code')
            if param_state is not None and code is not None:
                return redirect(url_for('auth.login', state=param_state, code=code))
            else:
                return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped_view

def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if session.get('is_admin') == False:
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped_view

@bp.route('/edit/password/', methods=('GET', 'POST'))
@login_required
def changepassword():
    if request.method == 'GET':
        return render_template('admin/changepassword.html')
    else: # i.e. if POST 
        (domain, method, is_admin) = get_login_session()
        existing_password = request.form.get('existing_password')
        new_password = request.form.get('new_password')
        repeat_password = request.form.get('repeat_password')
        error = None
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if new_password != repeat_password:
            error = 'New passwords do not match.'
        if method != 'changepasswordlink': # Check current password
            cursor.execute(sql_select, (domain,))
            results = cursor.fetchone()
            if results is None:
                error = 'Incorrect domain. Are you registered?'
            elif not results['password']:
                error = 'This account uses IndieAuth.'
            elif not check_password_hash(results['password'], existing_password):
                error = 'Incorrect existing password.'
        if error:
            flash(error)
            return render_template('admin/changepassword.html')
        else:
            cursor.execute(sql_change_password, (generate_password_hash(new_password), domain, ))
            conn.commit()
            return render_template('admin/success.html', title="Change password success", message="<p>You have successfully changed your password.</p>")

@bp.route('/forgotten/password/', methods=['GET'])
def forgottenpassword_get():
    key = request.args.get('key')
    if key:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_forgotten_password_login, (key,))
        results = cursor.fetchone()
        if results: # i.e. if there is a valid key that hasn't expired
            domain = results['domain']
            if domain:
                set_login_session(domain, "changepasswordlink")
                return redirect(url_for('auth.changepassword'))
            else:
                return render_template('admin/forgottenpassword.html')
        else:
            return render_template('admin/forgottenpassword.html')
    else:
        return render_template('admin/forgottenpassword.html')

@bp.route('/forgotten/password/', methods=['POST'])
#@login_required
#@admin_required
def forgottenpassword_post():
    domain = request.form.get('domain')
    email = request.form.get('email')
    if not domain:
        error = 'Please enter your domain.'
        flash(error)
        return render_template('admin/forgottenpassword.html')
    elif not email:
        error = 'Please enter your email.'
        flash(error)
        return render_template('admin/forgottenpassword.html')
    else:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_select, (domain,))
        results = cursor.fetchone()
        if results: # i.e. if the domain exists
            if results['contact_email']: # and there's a valid email
                if email == results['contact_email']:
                    forgotten_password_key = generate_validation_key(32)
                    cursor.execute(sql_forgotten_password, (forgotten_password_key, domain,))
                    conn.commit()
                    subject = "Email from searchmysite.net"
                    forgotten_password_link = get_host(request.base_url, request.headers)
                    text = 'Copy and paste this link into your web browser to reset your password:\n{}?key={}\n'.format(forgotten_password_link, forgotten_password_key)
                    success_status = send_email(None, email, subject, text)
                    return render_template('admin/success.html', title="Password reminder sent", message="<p>An email has been sent to your registered email address to allow you to change your password. It will be valid for 30 minutes.</p>")
                else:
                    error = 'Please enter your registered email address. If you have forgotten this, please use the Contact link.'
                    flash(error)
                    return render_template('admin/forgottenpassword.html')
            else:
                return render_template('admin/forgottenpassword.html')
        else:
            return render_template('admin/forgottenpassword.html')

def set_login_session(domain, method):
    session.clear()
    # Check if admin
    is_admin = False
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_select_admin, (domain,))
    admin = cursor.fetchone()
    if admin:
        is_admin = True
    # Update last_login time
    cursor.execute(sql_last_login_time, (domain,))
    conn.commit()
    # Set session variables
    session['logged_in_domain'] = domain
    session['log_in_method'] = method # valid values: usernamepassword, indieauth or changepasswordlink
    session['is_admin'] = is_admin
    current_app.logger.debug('logged_in_domain: {}, log_in_method: {}, is_admin: {}'.format(domain, method, is_admin))
    return

def get_login_session():
    domain = session['logged_in_domain'] 
    method = session['log_in_method']
    is_admin = session['is_admin'] 
    return (domain, method, is_admin)

# The IndieAuth workflow is described at https://indielogin.com/api but in summary:
# 1. Submit url,client_id,redirect_uri,state via a GET to https://indielogin.com/auth 
# 2. User logs in to indielogin.com
# 3. If user successfully logged in, they are redirected back to redirect_uri, also via a GET request, 
#    with state and code params. State must match the state in step 1.
# 4. POST code,redirect_uri,client_id to https://indielogin.com/auth and if successful response will be e.g.
#    {"me": "https://michael-lewis.com/"}
#
# There are 2 entry points to viaindieauth1:
# 1. Landing on the page for the first time or subsequent time if not validated. 
#    Using the absence of state and code params to determine if this is the case.
# 2. Landing on the page mid-validation.
# 
# From the 2nd entry point, there are 5 exits if it is part of the Add Site workflow:
# 1. On IndieAuth mid-validation, the states don't match
# 2. On IndieAuth step 4 there's an error code (non 200 response)
# 3. On IndieAuth step 4, domain has already been submitted and is fully validated
# 4. On IndieAuth step 4, domain has already been submitted, but not fully validated
# 5. On IndieAuth step 4, domain has not been submitted and there's no error
# And 4 exits if it is part of the Logon workflow:
# 1-3 As per Add Site workflow, with the difference that fully validated is successful logon
# 4. Not fully validated
# 
# UPDATE: This is no longer used by the add site workflow. add.step3 in add.py does its own IndieAuth login.
# The if addsite_workflow == True section could therefore be removed. Could look to do a new IndieAuth login 
# with 2 functions: 
# (i) just confirming they have IndieAuth login setup for that domain and can login to IndieAuth (for the add site workflow)
# (ii) as per (i) but with an additional check that the domain is present and enabled in searchmysite.net (for the searchmysite.net login workflow)
def do_indieauth_login(current_page, next_page, addsite_workflow, insertdomainsql):
    current_app.logger.debug('Starting do_indieauth_login')
    return_action = "redirect" # default, alternative is render_template
    return_target = current_page # default, alternative is next_page
    param_state = request.args.get('state')
    code = request.args.get('code')
    current_app.logger.debug('request.base_url: {}, request.host_url: {}, request.headers.get(\'X-Forwarded-Host\'): {}'.format(request.base_url, request.host_url, request.headers.get('X-Forwarded-Host')))
    if addsite_workflow or session.get('redirect_uri') is None: # Always use the current URL (base_url) for redirect_uri if in addsite_workflow, otherwise it'll pickup the login URL if they've clicked on a login protected URL before Add Site
        redirect_uri = get_host(request.base_url, request.headers) # need it to be e.g. https://searchmysite.net/admin/login/ (base_url) rather than https://searchmysite.net/admin/ (url_root)
        session['redirect_uri'] = redirect_uri
    else:
        redirect_uri = session.get('redirect_uri')
    if session.get('client_id') is None:
        client_id = get_host(request.host_url, request.headers) # need it to be https://searchmysite.net/ (host_url) rather than https://searchmysite.net/admin/ (url_root)
        session['client_id'] = client_id
    else:
        client_id = session.get('client_id')
    if session.get('state') is None:
        session_state = generate_validation_key(12)
        session['state'] = session_state
    else:
        session_state = session.get('state')
    current_app.logger.debug('redirect_uri: {}, client_id: {}, state: {}'.format(redirect_uri, client_id, session_state))
    # If they haven't been redirected back here by IndieAuth
    if param_state is None and code is None:
        current_app.logger.debug('Haven\'t been to IndieAuth yet')
        return_action = "render_template"
        return_target = current_page
    # If they have been redirected back here by IndieAuth
    else: 
        current_app.logger.debug('Redirected here by IndieAuth')
        if param_state != session_state: # step 3 check
            current_app.logger.error('Submitted state does not match returned state')
            error_message = 'Submitted state does not match returned state. Please try again.'
            flash(error_message)
            return_action = "render_template"
            return_target = current_page
        else: # step 4 check
            current_app.logger.debug('Submitted state matches returned state')
            indieauth = "https://indielogin.com/auth"
            headers = {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8', 'Accept': 'application/json'}
            payload = {'code': code, 'redirect_uri': redirect_uri, 'client_id': client_id}
            response = requests.post(indieauth, data=payload, headers=headers)
            responsejson = response.json()
            if response.status_code != 200:
                current_app.logger.error('Got an error code from IndieAuth')
                error = responsejson['error']
                error_description = responsejson['error_description']
                error_message = 'Unable to authenticate with IndieAuth: {} {}'.format(error, error_description)
                flash(error_message)
                return_action = "render_template"
                return_target = current_page
            else: # Success
                current_app.logger.info('Got a success code from IndieAuth')
                home_page = responsejson['me']
                domain = extract_domain(home_page)
                session['home_page'] = home_page
                conn = get_db()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(sql_select, (domain,))
                indexed_result = cursor.fetchone()
                if addsite_workflow == True:
                    # 3 routes through the add site workflow:
                    # 1. Domain submitted and fully validated, i.e. email entered
                    # 2. Domain submitted but not fully validated, i.e. email not entered
                    # 3. Domain not submitted at all)
                    cursor.execute(sql_select, (domain,))
                    pending_result = cursor.fetchone()
                    if indexed_result is not None and indexed_result['owner_verified'] == True: # i.e. fully validated and owner_verified (existing but non owner_verified should pass through to next step)
                        current_app.logger.info('Add site: domain already submitted and fully validated')
                        error_message = 'This domain has already been registered. Click Manage My Site to manage it, or try submitting a different domain.'
                        flash(error_message)
                        return_action = "render_template"
                        return_target = current_page
                    elif pending_result is not None: # i.e. domain submitted but verification process not complete 
                        # e.g. people who submit the domain but decide not to enter their email
                        # but then revisit at a later time to complete the process
                        # Note that this will appear to the user as though they had never submitted at all, given they have to go through step 1 to get to step 2 
                        # but unknown to them their entry will be in the tblPendingDomains and they will benefit from an earlier date_domain_added
                        current_app.logger.info('Add site: domain submitted but not fully validated, so redirecting to next step')
                        return_action = "redirect"
                        return_target = next_page
                    else: # i.e. domain hasn't already been submitted
                        current_app.logger.info('Add site: domain not already submitted, so submitting and redirecting to next step')
                        cursor.execute(insertdomainsql, (domain, home_page, 'IndieAuth'))
                        conn.commit()
                        return_action = "redirect"
                        return_target = next_page
                else: # if logon workflow
                    if indexed_result is not None and indexed_result['owner_verified'] == True and indexed_result['contact_email'] is not None:
                        set_login_session(domain, "indieauth")
                        return_action = "redirect"
                        return_target = next_page
                        current_app.logger.info('Login: success')
                    else:
                        return_action = "redirect"
                        return_target = url_for('auth.login')
                        current_app.logger.error('Login: fail, {} to {}'.format(return_action, return_target))
    return return_action, return_target
