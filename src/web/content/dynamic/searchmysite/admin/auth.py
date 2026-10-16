import functools
import psycopg2.extras
from os import environ
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app
)
from werkzeug.security import check_password_hash, generate_password_hash
from urllib.parse import urlparse
import requests
from searchmysite.db import get_db
from searchmysite.adminutils import generate_validation_key, extract_domain, send_email, get_host
import searchmysite.sql


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
        cursor.execute(searchmysite.sql.sql_select_login_details, (domain,))
        results = cursor.fetchone()
        if results is None:
            error = 'Incorrect domain. Are you registered?'
        elif not results['status'] == 'ACTIVE' and not (results['tier'] == 2 or results['tier'] == 3):
            error = 'You don\'t have an active Full or Free Trial subscription. Please subscribe.'
        elif not check_password_hash(results['password'], password):
            error = 'Incorrect password.'
        if error is None:
            # Get next_page before set_login_session, because it clears the session
            next_page = get_next_page()
            set_login_session(domain, "usernamepassword")
            return redirect(next_page or url_for('manage.manage'))
        flash(error)
        return render_template('admin/login.html')
    else:
        current_page = 'admin/login.html'
        next_page = get_next_page() or url_for('manage.manage')
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
                session['next_page'] = request.url
                return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped_view

def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if session.get('is_admin') == False:
            session['next_page'] = request.url
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
            cursor.execute(searchmysite.sql.sql_select_login_details, (domain,))
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
            cursor.execute(searchmysite.sql.sql_change_password, (generate_password_hash(new_password), domain, ))
            conn.commit()
            return render_template('admin/success.html', title="Change password success", message="<p>You have successfully changed your password.</p>")

@bp.route('/forgotten/password/', methods=['GET'])
def forgottenpassword_get():
    key = request.args.get('key')
    if key:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(searchmysite.sql.sql_forgotten_password_login, (key,))
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
        cursor.execute(searchmysite.sql.sql_select_login_details, (domain,))
        results = cursor.fetchone()
        if results: # i.e. if the domain exists
            if results['email']: # and there's a valid email
                if email == results['email']:
                    forgotten_password_key = generate_validation_key(32)
                    cursor.execute(searchmysite.sql.sql_forgotten_password, (forgotten_password_key, domain,))
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

# Returns the URL the user was trying to reach before being redirected to login,
# or None if there is none (or it is not a valid internal URL).
# The value is removed from the session when a login succeeds, because set_login_session clears it.
def get_next_page():
    next_page = session.get('next_page')
    if next_page:
        parsed = urlparse(next_page)
        if parsed.netloc and parsed.netloc != request.host: # i.e. if it is an external URL
            current_app.logger.warn('Ignoring external next_page in session: {}'.format(next_page))
            session.pop('next_page', None)
            return None
    return next_page

def set_login_session(domain, method):
    session.clear()
    # Check if admin
    is_admin = False
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(searchmysite.sql.sql_select_admin, (domain,))
    admin = cursor.fetchone()
    if admin:
        is_admin = True
    # Update last_login time
    cursor.execute(searchmysite.sql.sql_last_login_time, (domain,))
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
