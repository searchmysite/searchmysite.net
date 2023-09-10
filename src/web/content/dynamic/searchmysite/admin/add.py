from flask import (
    Blueprint, flash, redirect, render_template, request, session, url_for, current_app
)
from werkzeug.security import generate_password_hash
import psycopg2.extras
from os import environ
from searchmysite.db import get_db
import searchmysite.sql
from searchmysite.adminutils import extract_domain, generate_validation_key, check_for_validation_key, get_host, insert_subscription
import requests
import subprocess


bp = Blueprint('add', __name__)


# User message strings

verification_failed_message = 'Unfortunately the site ownership verification failed. Please ensure it is configured correctly and try again.'
indexing_check_failed_message = 'Unfortunately your site cannot currently be indexed. There could be a number of reasons for this, e.g. robots.txt or Cloudflare blocking indexing. Please make the necessary changes and try again, or use the Contact link to request further information.'


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
        # Check if home page has been submitted already and if so what the status of the highest tier is
        # Note that the highest tier might not be the active tier, i.e. it might have an EXPIRED tier 3 and ACTIVE tier 1 listing
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(searchmysite.sql.sql_select_highest_tier, (domain,))
        highest_tier = cursor.fetchone()
        # Get the current active tier
        # Note that the current active tier might not be the highest tier
        current_active_tier = get_active_tier(domain)
        # See if the newly selected tier already exists or not. This is to determine if insert or update statements are required
        new_tier_exists = False
        if highest_tier and highest_tier['tier'] == tier:
            new_tier_exists = True
        # Route to the next stage of the Add Site workflow
        if not home_page or not site_category or not tier: # There is client-side validation so this shouldn't be possible
            message = 'Please enter the required fields.'
            flash(message)
            return render_template('admin/add.html', tiers=tiers)
        elif not highest_tier: # Domain hasn't previously been submitted
            cursor.execute(searchmysite.sql.sql_insert_domain, (domain, home_page, site_category))
            conn.commit()
            if tier == 1:
                cursor.execute(searchmysite.sql.sql_insert_basic_listing, (domain, tier))
                conn.commit()
                return render_template('admin/add-success.html', tier=tier)
            elif tier == 2 or tier == 3:
                start_freefull_approval_session(domain, home_page, tier, new_tier_exists)
                return redirect(url_for('add.step1'))
        elif current_active_tier > 0: # Domain already has an active listing
            if tier > current_active_tier: # The user has selected to upgrade the tier 
                start_freefull_approval_session(domain, home_page, tier, new_tier_exists)
                return redirect(url_for('add.step1'))
            else: # If they're not upgrading, i.e. staying the same or resubmitting as a lower tier
                message = 'The domain {} already has an active tier {} listing with a home page at {}.'.format(domain, current_active_tier, highest_tier['home_page'])
                if tier == current_active_tier:
                    message = message + ' If you would like to upgrade the listing please resubmit with a higher tier.'
                flash(message)
                return redirect(url_for('add.add'))
        elif highest_tier['moderator_approved'] == False or highest_tier['indexing_enabled'] == False: # Rejected or indexing disabled
            if highest_tier['moderator_approved'] == False:
                message = 'Domain {} has previously been submitted but rejected for the following reason: {}. '.format(domain, highest_tier['moderator_action_reason'])
            if highest_tier['indexing_enabled'] == False:
                message = 'Domain {} has had indexing disabled for the following reason: {}. '.format(domain, highest_tier['indexing_disabled_reason'])
            message += 'Please use the Contact link if you would like to query this.'
            flash(message)
            return redirect(url_for('add.add'))
        elif highest_tier['status'] == 'PENDING':
            if highest_tier['tier'] == 1 and highest_tier['pending_state'] == 'MODERATOR_REVIEW':
                message = 'Domain {} is currently pending moderator review.'.format(domain)
                flash(message)
                return redirect(url_for('add.add'))
            elif highest_tier['tier'] == 2 or highest_tier['tier'] == 3:
                session['home_page'] = home_page
                if highest_tier['pending_state'] == 'LOGIN_AND_VALIDATION_METHOD':
                    return redirect(url_for('add.step1'))
                elif highest_tier['pending_state'] == 'EMAIL' or highest_tier['pending_state'] == 'EMAIL_AND_PASSWORD':
                    return redirect(url_for('add.step2'))
                elif highest_tier['pending_state'] == 'INDIEAUTH_LOGIN' or highest_tier['pending_state'] == 'VALIDATION_CHECK':
                    return redirect(url_for('add.step3'))
                elif highest_tier['pending_state'] == 'PAYMENT':
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
            cursor.execute(searchmysite.sql.sql_update_freefull_step1, (include_public, login_type, domain, pending_state, domain, tier))
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
                cursor.execute(searchmysite.sql.sql_update_freefull_step2, (email, password, domain, pending_state, domain, tier, domain, validation_method, validation_key))
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
            cursor.execute(searchmysite.sql.sql_select_validation_key, (domain,))
            result = cursor.fetchone()
            validation_key = result['validation_key']
            if request.method == 'GET':
                return render_template('admin/add-step3-validate.html', domain=domain, tier=tier, login_type=login_type, validation_key=validation_key)
            else:
                prefix = 'searchmysite-verification'
                validation_method = check_for_validation_key(domain, prefix, validation_key)
                if validation_method == 'DCV': # i.e. if the ownership verification has succeeded
                    indexable = check_a_site_can_be_indexed(domain, home_page)
                    if indexable: # i.e. if the site is indexable
                        cursor.execute(searchmysite.sql.sql_update_freefull_validated, (domain,))
                        conn.commit()
                        if current_app.config['ENABLE_PAYMENT'] == True and tier == 3:
                            cursor.execute(searchmysite.sql.sql_update_freefull_step3, (domain, tier))
                            conn.commit()
                            return redirect(url_for('add.step4'))
                        else:
                            return redirect(url_for('add.success'))
                    else:
                        current_app.logger.warn('check_a_site_can_be_indexed failed for {}'.format(domain))
                        flash(indexing_check_failed_message)
                        return render_template('admin/add-step3-validate.html', domain=domain, tier=tier, login_type=login_type, validation_key=validation_key)
                else:
                    current_app.logger.warn('check_for_validation_key failed for {}'.format(domain))
                    flash(verification_failed_message)
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
                        indexable = check_a_site_can_be_indexed(domain, home_page)
                        if indexable: # i.e. if the site is indexable
                            conn = get_db()
                            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                            cursor.execute(searchmysite.sql.sql_update_freefull_validated, (domain,))
                            conn.commit()
                            if current_app.config['ENABLE_PAYMENT'] == True and tier == 3:
                                cursor.execute(searchmysite.sql.sql_update_freefull_step3, (domain, tier))
                                conn.commit()
                                return redirect(url_for('add.step4'))
                            else:
                                return redirect(url_for('add.success'))
                        else:
                            flash(indexing_check_failed_message)
                            return render_template('admin/add-step3-validate.html', domain=domain, tier=tier, login_type=login_type)


@bp.route('/add/step4/', methods=('GET', 'POST'))
def step4():
    (home_page, domain, tier, login_type, site_category) = get_session_data()
    if not home_page:
        return redirect(url_for('add.add'))
    else:
        return render_template('admin/add-step4-payment.html', tier=tier, login_type=login_type)

@bp.route('/add/success/')
def success():
    (home_page, domain, tier, login_type, site_category) = get_session_data()
    if not home_page:
        current_app.logger.debug('No home page. Session data: home_page {}, domain {}, tier {}, login_type {}, site_category {}'.format(home_page, domain, tier, login_type, site_category))
        return redirect(url_for('add.add'))
    else:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        current_app.logger.info('Finishing listing for domain {}, tier {}'.format(domain, tier))
        if tier == 2 or tier == 3:
            insert_subscription(domain, tier)
            cursor.execute(searchmysite.sql.sql_update_freefull_approved, (domain, domain, tier, tier, domain))
            current_app.logger.info('Successfully finished listing for domain {}'.format(domain))
        conn.commit()
    return render_template('admin/add-success.html', tier=tier, login_type=login_type)


# Utilities

# Fields in tblTiers:
# tier_no, tier_name, 
# default_full_reindex_frequency, default_incremental_reindex_frequency, default_indexing_page_limit, default_on_demand_reindexing, default_api_enabled, 
# cost_amount, cost_currency, listing_duration
def get_tier_data():
    tiers = []
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(searchmysite.sql.sql_select_tiers)
    results = cursor.fetchall()
    if results:
        for result in results:
            tier = {}
            # tier_no
            tier['tier'] = result['tier']
            # tier_name
            tier['tier_name'] = result['tier_name']
            # full_reindex_frequency
            full_reindex_frequency = str(result['default_full_reindex_frequency'])
            if full_reindex_frequency.endswith(', 0:00:00'): # Only tidies whole and half days for now
                full_reindex_frequency = full_reindex_frequency.replace(', 0:00:00', '')
            elif full_reindex_frequency.endswith(', 12:00:00'):
                full_reindex_frequency = full_reindex_frequency.replace(', 12:00:00', ' 12 hrs')
            tier['full_reindex_frequency'] = full_reindex_frequency 
            # incremental_reindex_frequency
            incremental_reindex_frequency = str(result['default_incremental_reindex_frequency'])
            if incremental_reindex_frequency.endswith(', 0:00:00'):
                incremental_reindex_frequency = incremental_reindex_frequency.replace(', 0:00:00', '')
            elif incremental_reindex_frequency.endswith(', 12:00:00'):
                incremental_reindex_frequency = incremental_reindex_frequency.replace(', 12:00:00', ' 12 hrs')
            tier['incremental_reindex_frequency'] = incremental_reindex_frequency 
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

# Return the active tier number (1, 2 or 3) or 0 if there is no active tier
def get_active_tier(domain):
    active_tier = 0
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(searchmysite.sql.sql_select_active_tier, (domain,))
    active_tier_results = cursor.fetchone()
    if active_tier_results:
        active_tier = int(active_tier_results['tier'])
    current_app.logger.debug('Current active tier: {}.'.format(active_tier))
    return active_tier

# Get previously entered data, using home page in session
def get_session_data():
    home_page = session.get('home_page')
    domain = extract_domain(home_page)
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(searchmysite.sql.sql_select_highest_tier, (domain,))
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

def start_freefull_approval_session(domain, home_page, tier, new_tier_exists):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if new_tier_exists:
        cursor.execute(searchmysite.sql.sql_update_freefull_listing, (domain, tier))
    else:
        cursor.execute(searchmysite.sql.sql_insert_freefull_listing, (domain, tier))
    conn.commit()
    session.clear()
    session['home_page'] = home_page
    return

def check_a_site_can_be_indexed(domain, home_page):
    current_app.logger.debug('Running check_a_site_can_be_indexed for domain {} with home page {}'.format(domain, home_page))
    indexable = False # Assume a site can't be indexed
    process_output = subprocess.run(['scrapy', 'shell', '-s', 'ROBOTSTXT_OBEY=True', '-s', "USER_AGENT='Mozilla/5.0 (compatible; SearchMySiteBot/1.0; +https://searchmysite.net)'", '--nolog', home_page, '-c', 'response'], capture_output=True)
    if process_output.stdout.decode().startswith('<200'): indexable = True
    current_app.logger.debug('check_a_site_can_be_indexed return value {} and full response: {}'.format(indexable, process_output.stdout.decode()))
    return indexable
