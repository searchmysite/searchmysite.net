from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app
)
from werkzeug.exceptions import abort
from markupsafe import escape
import psycopg2.extras
from psycopg2.extensions import AsIs
from os import environ
from datetime import datetime, timezone
import json
import config
from searchmysite.admin.auth import login_required, set_login_session, get_login_session
from searchmysite.db import get_db
from searchmysite.adminutils import delete_domain, insert_subscription
import searchmysite.sql


bp = Blueprint('manage', __name__)


# These are the forms on Manage Site
# label must match the database field name
# Manage Site / Site details
manage_details_form = [
{'label':'domain', 'label-text':'Domain', 'type':'text', 'class':'form-control-plaintext', 'editable':False, 'help':'Only pages on this domain will be indexed. This your login ID if you use a password.'},
{'label':'home_page', 'label-text':'Home page', 'type':'text', 'class':'form-control-plaintext', 'editable':False, 'help':'The page where indexing will begin. This is your login ID if you use IndieAuth.'},
{'label':'category', 'label-text':'Category', 'type':'text', 'class':'form-control-plaintext', 'editable':False, 'help':'The site category. Users might filter search results to certain categories.'},
{'label':'domain_first_submitted', 'label-text':'Domain added', 'type':'text', 'class':'form-control-plaintext', 'editable':False, 'help':'The time and date this domain was first entered into the system.'},
{'label':'login_type', 'label-text':'Login method', 'type':'text', 'class':'form-control-plaintext', 'editable':False, 'help':'The method you use to login. Options are PASSWORD (login ID is the domain and password is required) and INDIEAUTH (login ID is the home page and no password is required in this system).'},
{'label':'email', 'label-text':'Admin email', 'type':'email', 'class':'form-control', 'editable':True, 'help':'Site admin email address. Only used for service updates.'},
{'label':'api_enabled', 'label-text':'API enabled', 'type':'text', 'class':'form-control-plaintext', 'editable':False, 'help':'Whether you have the API enabled for your domain or not.'},
]

# Manage Site / Indexing
# Notes:
# There isn't a database field for next_reindex - this will be populated in get_manage_data based on indexing_status, indexing_status_changed and full_reindex_frequency
# There aren't database fields for web_feed and sitemap - this will be populated in get_manage_data based on web_feed_auto_discovered and web_feed_user_entered
manage_indexing_form = [
{'label':'indexing_enabled', 'label-text':'Indexing enabled', 'type':'text', 'class':'form-control-plaintext', 'editable':False, 'help':'True if indexing is enabled, and False if indexing is disabled (e.g. because of repeated failed indexing attempts).'},
{'label':'include_in_public_search', 'label-text':'Include in public search', 'type':'text', 'class':'form-control-plaintext', 'editable':False, 'help':'True if content from this site is to be included in the public search (along with Browse, Newest and Random).'},
{'label':'indexing_status', 'label-text':'Indexing current status', 'type':'text', 'class':'form-control-plaintext', 'editable':False, 'help':'The latest status of indexing (either RUNNING, COMPLETE, PENDING).'},
{'label':'indexing_status_changed', 'label-text':'Indexing status last updated', 'type':'text', 'class':'form-control-plaintext', 'editable':False, 'help':'The time the indexing status was last changed.'},
{'label':'full_reindex_frequency', 'label-text':'Full reindexing frequency', 'type':'text', 'class':'form-control-plaintext', 'editable':False, 'help':'The time period between full reindexes of the site.'},
{'label':'next_reindex', 'label-text':'Next full reindex', 'type':'text', 'class':'form-control-plaintext', 'editable':False, 'help':'Earliest start time for the next full reindex.'},
{'label':'web_feed', 'label-text':'Web feed', 'type':'text', 'class':'form-control', 'editable':True, 'help':'This is the web feed (RSS or Atom), used for indexing and for identifying pages which are part of a feed. The system tries to identify a feed but it can be entered or overridden here.'},
{'label':'indexing_page_limit', 'label-text':'Indexing page limit', 'type':'text', 'class':'form-control-plaintext', 'editable':False, 'help':'The maximum number of pages on your domain which will be indexed.'},
{'label':'content_chunks_limit', 'label-text':'Maximum vector search embeddings', 'type':'text', 'class':'form-control-plaintext', 'editable':False, 'help':'The maximum number of page content chunks which will be converted to embeddings for vector search. Any content beyond this will not be searchable via the vector search.'},
{'label':'indexing_type', 'label-text':'Indexing type', 'type':'text', 'class':'form-control-plaintext', 'editable':False, 'help':'What mechanism is used to index the site. In almost all cases it will be the default spider.'},
]


# Routes
# Routes end users will see and potentially bookmark

@bp.route('/manage/')
def manage():
    return redirect(url_for('manage.sitedetails'))

@bp.route('/manage/sitedetails/', methods=('GET', 'POST'))
@login_required
def sitedetails():
    (domain, method, is_admin) = get_login_session()
    if request.method == 'GET':
        manage_details_data = get_manage_data(domain, manage_details_form)
        return render_template('admin/manage-sitedetails.html', manage_details_form=manage_details_form, manage_details_data=manage_details_data)
    else: # i.e. if POST
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if request.form.get('edited-field'):
            edited_field_name = request.form.get('edited-field')
            if any(row['label'] == edited_field_name for row in manage_details_form): # Make sure a label with that value exists
                edited_field_value = request.form.get(edited_field_name)
                current_app.logger.debug('edited field name: {}, value: {}'.format(edited_field_name, edited_field_value))
                cursor.execute(searchmysite.sql.sql_update_value, (AsIs(edited_field_name), edited_field_value, domain,))
                conn.commit()
        manage_details_data = get_manage_data(domain, manage_details_form)
        return render_template('admin/manage-sitedetails.html', manage_details_form=manage_details_form, manage_details_data=manage_details_data)

@bp.route('/manage/indexing/', methods=('GET', 'POST'))
@login_required
def indexing():
    (domain, method, is_admin) = get_login_session()
    if request.method == 'GET':
        manage_indexing_data = get_manage_data(domain, manage_indexing_form)
        return render_template('admin/manage-indexing.html', manage_indexing_form=manage_indexing_form, manage_indexing_data=manage_indexing_data)
    else: # i.e. if POST
        # Each row in the template is a form, so there should only be one field per form submission
        # If they've edited a field, find the field, make sure that field exists in the database, and update database
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if request.form.get('edited-field'):
            edited_field_name = request.form.get('edited-field')
            if any(row['label'] == edited_field_name for row in manage_indexing_form): # Make sure a label with that value exists
                if edited_field_name == 'web_feed':
                    edited_field_value = request.form.get('web_feed')
                    edited_field_name = 'web_feed_user_entered'
                else:
                    edited_field_value = request.form.get(edited_field_name)
                current_app.logger.debug('edited field name: {}, value: {}'.format(edited_field_name, edited_field_value))
                cursor.execute(searchmysite.sql.sql_update_value, (AsIs(edited_field_name), edited_field_value, domain,))
                conn.commit()
        # If they've clicked Delete Path or Save Path in Exclude Path section
        if request.form.get('delete_exclude_path'):
            delete_exclude_path = request.form.get('delete_exclude_path')
            #current_app.logger.debug('delete_exclude_path: {}'.format(delete_exclude_path))
            cursor.execute(searchmysite.sql.sql_delete_filter, (domain, "path", delete_exclude_path, ))
            conn.commit()
        if request.form.get('save_exclude_path'):
            save_exclude_path = request.form.get('save_exclude_path')
            #current_app.logger.debug('save_exclude_path: {}'.format(save_exclude_path))
            cursor.execute(searchmysite.sql.sql_insert_filter, (domain, "path", save_exclude_path, ))
            conn.commit()
        # If they've clicked Type Path or Save Type in Exclude Type section
        if request.form.get('delete_exclude_type'):
            delete_exclude_type = request.form.get('delete_exclude_type')
            #current_app.logger.debug('delete_exclude_type: {}'.format(delete_exclude_type))
            cursor.execute(searchmysite.sql.sql_delete_filter, (domain, "type", delete_exclude_type, ))
            conn.commit()
        if request.form.get('save_exclude_type'):
            save_exclude_type = request.form.get('save_exclude_type')
            #current_app.logger.debug('save_exclude_type: {}'.format(save_exclude_type))
            cursor.execute(searchmysite.sql.sql_insert_filter, (domain, "type", save_exclude_type, ))
            conn.commit()
        manage_indexing_data = get_manage_data(domain, manage_indexing_form)
        return render_template('admin/manage-indexing.html', manage_indexing_form=manage_indexing_form, manage_indexing_data=manage_indexing_data)

@bp.route('/manage/subscriptions/')
@login_required
def subscriptions():
    (domain, method, is_admin) = get_login_session()
    subscriptions = get_subscription_data(domain)
    tier = get_tier_data(domain)
    return render_template('admin/manage-subscriptions.html', subscriptions=subscriptions, tier=tier)

@bp.route('/delete/', methods=('GET', 'POST'))
@login_required
def delete():
    if request.method == 'GET':
        return render_template('admin/delete.html')
    else: # i.e. if POST 
        (domain, method, is_admin) = get_login_session()
        delete_domain(domain)
        # Construct message
        message = "<p>Your site has been successfully deleted.</p>"
        message += "<p>You can confirm there are no documents left in the search collection via " 
        message += '<a href="/search/?q=domain:{}">a search for domain:{}</a>.</p>'.format(domain, domain)
        message += '<p>Sorry to see you go. But you can always come back via <a href="{}">Add Site</a>.</p>'.format(url_for('add.add'))
        return render_template('admin/success.html', title="Delete My Site Success", message=message)

@bp.route('/reindex/')
@login_required
def reindex():
    (domain, method, is_admin) = get_login_session()
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(searchmysite.sql.sql_update_indexing_status, (domain, domain, ))
    conn.commit()
    message = 'The site has been queued for reindexing. You can check on progress by refreshing this page.'
    flash(message)
    return redirect(url_for('manage.indexing'))

# Routes end users won't see and so shouldn't bookmark

@bp.route('/manage/subscriptions/renew-success/')
@login_required
def renew_subscription_success():
    (domain, method, is_admin) = get_login_session()
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(searchmysite.sql.sql_select_tier, (domain,))
    result = cursor.fetchone()
    if result:
        if result['tier'] == 2:
            current_app.logger.info('Current tier for {} is tier 2, and user has pressed Purchase, so need to upgrade to tier 3'.format(domain))
            cursor.execute(searchmysite.sql.sql_upgrade_tier2_to_tier3, (domain, domain, domain,))
            conn.commit()
    tier = 3 # Hardcoding to tier 3 for now given it is the only paid for option at the moment (if they're currently tier 2 we don't want them paying to renew tier 2)
    current_app.logger.info('Purchasing subscription for domain {}, tier {}'.format(domain, tier))
    insert_subscription(domain, tier)
    message = 'Subscription successfully purchased for domain {}'.format(domain)
    current_app.logger.info(message)
    flash(message)
    return redirect(url_for('manage.subscriptions'))


# Utilities

def get_manage_data(domain, manage_form):
    manage_data = {}
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(searchmysite.sql.sql_select_domains, (domain,))
    result = cursor.fetchone()
    # Get data matching all the fields on the form spec, with exceptions for next_reindex web_feed
    for form_item in manage_form:
        label = form_item['label']
        if label != 'next_reindex' and label != 'web_feed' and result[label]:
            if label == 'indexing_enabled' and result['indexing_disabled_reason']: # There's logic in the template to show reason if indexing disabled
                manage_data['indexing_disabled_reason'] = result['indexing_disabled_reason']
            elif label == 'domain_first_submitted' and result['domain_first_submitted']:
                manage_data['domain_first_submitted'] = result['domain_first_submitted'].strftime('%d %b %Y, %H:%M%z')
            elif label == 'indexing_status_changed' and result['indexing_status_changed']:
                manage_data['indexing_status_changed'] = result['indexing_status_changed'].strftime('%d %b %Y, %H:%M%z')
            else:
                manage_data[label] = result[label]
        elif label == 'next_reindex':
            if result['indexing_status'] == 'PENDING':
                next_reindex = "Any time now"
            elif result['indexing_status_changed'] and result['full_reindex_frequency']:
                next_reindex_datetime = result['indexing_status_changed'] + result['full_reindex_frequency']
                next_reindex = next_reindex_datetime.strftime('%d %b %Y, %H:%M%z')
            else: # This shouldn't happen, but just in case
                next_reindex = "Not quite sure"
            manage_data['next_reindex'] = next_reindex
        elif label == 'web_feed':
            web_feed_auto_discovered = result['web_feed_auto_discovered']
            web_feed_user_entered = result['web_feed_user_entered']
            if web_feed_user_entered:
                web_feed = web_feed_user_entered
            elif web_feed_auto_discovered:
                web_feed = web_feed_auto_discovered
            else:
                web_feed = ""
            manage_data['web_feed'] = web_feed
    # Additional data
    if result['on_demand_reindexing']:
        manage_data['on_demand_reindexing'] = result['on_demand_reindexing']
    exclude_paths = []
    exclude_types = []
    cursor.execute(searchmysite.sql.sql_select_filters, (domain,))
    filter_results = cursor.fetchall()
    if filter_results:
        for filter in filter_results:
            if filter['action'] == 'exclude': # Just handling exclusions for now
                if filter['type'] == 'path': exclude_paths.append(filter['value'])
                if filter['type'] == 'type': exclude_types.append(filter['value'])
    manage_data['exclude_paths'] = exclude_paths
    manage_data['exclude_types'] = exclude_types
    return manage_data

def get_tier_data(domain):
    tier = {}
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(searchmysite.sql.sql_select_tier, (domain,))
    results = cursor.fetchall()
    if results:
        for result in results:
        #current_app.logger.debug('Status {}'.format(result['status']))
            if result['status']:
                tier['status'] = result['status']
            if result['tier_name']:
                tier['tier_name'] = result['tier_name']
            if result['listing_end']:
                tier['listing_end'] = result['listing_end']
    return tier

def get_subscription_data(domain):
    subscriptions = []
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(searchmysite.sql.sql_select_subscriptions, (domain,))
    results = cursor.fetchall()
    if results:
        for result in results:
            subscription = {}
            if result['tier_name']:
                subscription['tier_name'] = result['tier_name'] + ' Tier'
            if result['subscribed']:
                subscription['subscribed'] = result['subscribed']
            if result['subscription_start']:
                subscription['subscription_start'] = result['subscription_start']
            if result['subscription_end']:
                subscription['subscription_end'] = result['subscription_end']
            dt = datetime.now(timezone.utc)
            now_utc = dt.replace(tzinfo=timezone.utc)
            if now_utc > result['subscription_start'] and now_utc < result['subscription_end']:
                subscription['status'] = "Current"
            elif now_utc > result['subscription_end']:
                subscription['status'] = "Expired"
            elif now_utc < result['subscription_start']:
                subscription['status'] = "Future"
            else:
                subscription['status'] = "Unknown"
            subscriptions.append(subscription)
    return subscriptions
