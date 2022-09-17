from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, current_app
)
from werkzeug.exceptions import abort
from markupsafe import escape
import psycopg2.extras
from os import environ
from datetime import datetime, timezone
import json
import config
from searchmysite.admin.auth import login_required, set_login_session, get_login_session
from searchmysite.db import get_db
from searchmysite.util import delete_domain, insert_subscription

bp = Blueprint('manage', __name__)


# SQL

sql_select_domains = "SELECT * FROM tblDomains WHERE domain = (%s);"
sql_select_filters = "SELECT * FROM tblIndexingFilters WHERE domain = (%s);"
sql_select_subscriptions = "SELECT t.tier_name, s.subscribed, s.subscription_start, s.subscription_end, s.payment FROM tblSubscriptions s INNER JOIN tblTiers t on s.tier = t.tier WHERE DOMAIN = (%s) ORDER BY s.subscription_start ASC;"
sql_update_email = "UPDATE tblDomains SET email = (%s) WHERE domain = (%s);"
sql_insert_filter = "INSERT INTO tblIndexingFilters VALUES ((%s), 'exclude', (%s), (%s));"
sql_delete_filter = "DELETE FROM tblIndexingFilters WHERE domain = (%s) AND action = 'exclude' AND type = (%s) AND VALUE = (%s);"
sql_update_indexing_status = "UPDATE tblDomains SET full_indexing_status = 'PENDING', full_indexing_status_changed = now() WHERE domain = (%s); "\
    "INSERT INTO tblIndexingLog VALUES ((%s), 'PENDING', now());"
sql_select_tier = "SELECT l.status, l.tier, t.tier_name, l.listing_end FROM tblListingStatus l INNER JOIN tblTiers t ON t.tier = l.tier WHERE l.domain = (%s) AND l.status = 'ACTIVE' ORDER BY tier DESC LIMIT 1;"
sql_upgrade_tier2_to_tier3 = "UPDATE tblListingStatus SET status = 'EXPIRED', status_changed = NOW() WHERE domain = (%s) AND tier = 2; "\
    "INSERT INTO tblListingStatus (domain, tier, status, status_changed, listing_start, listing_end) "\
    "VALUES ((%s), 3, 'ACTIVE', NOW(), NOW(), NOW() + (SELECT listing_duration FROM tblTiers WHERE tier = 3)) "\
    "  ON CONFLICT (domain, tier) "\
    "  DO UPDATE SET "\
    "    status = EXCLUDED.status, "\
    "    status_changed = EXCLUDED.status_changed, "\
    "    listing_start = EXCLUDED.listing_start, "\
    "    listing_end = EXCLUDED.listing_end;"

# Routes
# Routes end users will see and potentially bookmark

@bp.route('/manage/')
def manage():
    return redirect(url_for('manage.sitedetails'))

@bp.route('/manage/sitedetails/')
@login_required
def sitedetails():
    (domain, method, is_admin) = get_login_session()
    result, next_reindex, exclude_paths, exclude_types = get_manage_data(domain)
    return render_template('admin/manage-sitedetails.html', result=result, edit=False)

@bp.route('/manage/indexing/', methods=('GET', 'POST'))
@login_required
def indexing():
    (domain, method, is_admin) = get_login_session()
    result, next_reindex, exclude_paths, exclude_types = get_manage_data(domain)
    if request.method == 'GET':
        return render_template('admin/manage-indexing.html', result=result, next_reindex=next_reindex, exclude_paths=exclude_paths, exclude_types=exclude_types, add_path=False, add_type=False)
    else: # i.e. if POST
        add = request.form.get("add")
        if add == "exclude_path":
            return render_template('admin/manage-indexing.html', result=result, next_reindex=next_reindex, exclude_paths=exclude_paths, exclude_types=exclude_types, add_path=True, add_type=False)
        elif add == "exclude_type":
            return render_template('admin/manage-indexing.html', result=result, next_reindex=next_reindex, exclude_paths=exclude_paths, exclude_types=exclude_types, add_path=False, add_type=True)
        else:
            save_exclude_path = request.form.get("save_exclude_path")
            save_exclude_type = request.form.get("save_exclude_type")
            if save_exclude_path:
                conn = get_db()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(sql_insert_filter, (domain, "path", save_exclude_path, ))
                conn.commit()
            if save_exclude_type:
                conn = get_db()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(sql_insert_filter, (domain, "type", save_exclude_type, ))
                conn.commit()
            return redirect(url_for('manage.indexing'))

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

# Routes end users won't see and so shouldn't bookmark

@bp.route('/manage/sitedetails/edit/', methods=('GET', 'POST'))
@login_required
def sitedetails_edit():
    (domain, method, is_admin) = get_login_session()
    result, next_reindex, exclude_paths, exclude_types = get_manage_data(domain)
    if request.method == 'GET':
        return render_template('admin/manage-sitedetails.html', result=result, edit=True)
    else: # i.e. if POST
        new_email = request.form.get("email")
        if new_email:
            conn = get_db()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute(sql_update_email, (new_email, domain,))
            conn.commit()
        return redirect(url_for('manage.sitedetails'))

@bp.route('/manage/indexing/delete/', methods=('GET', 'POST'))
@login_required
def indexing_delete():
    (domain, method, is_admin) = get_login_session()
    delete_exclude_path = request.form.get("delete_exclude_path")
    delete_exclude_type = request.form.get("delete_exclude_type")
    if delete_exclude_path:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_delete_filter, (domain, "path", delete_exclude_path, ))
        conn.commit()
    if delete_exclude_type:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_delete_filter, (domain, "type", delete_exclude_type, ))
        conn.commit()
    return redirect(url_for('manage.indexing'))

@bp.route('/manage/subscriptions/renew-success/')
@login_required
def renew_subscription_success():
    (domain, method, is_admin) = get_login_session()
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_select_tier, (domain,))
    result = cursor.fetchone()
    if result:
        if result['tier'] == 2:
            current_app.logger.info('Current tier for {} is tier 2, and user has pressed Purchase, so need to upgrade to tier 3'.format(domain))
            cursor.execute(sql_upgrade_tier2_to_tier3, (domain, domain,))
            conn.commit()
    tier = 3 # Hardcoding to tier 3 for now given it is the only paid for option at the moment (if they're currently tier 2 we don't want them paying to renew tier 2)
    current_app.logger.info('Purchasing subscription for domain {}, tier {}'.format(domain, tier))
    insert_subscription(domain, tier)
    message = 'Subscription successfully purchased for domain {}'.format(domain)
    current_app.logger.info(message)
    flash(message)
    return redirect(url_for('manage.subscriptions'))

@bp.route('/reindex/')
@login_required
def reindex():
    (domain, method, is_admin) = get_login_session()
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_update_indexing_status, (domain, domain, ))
    conn.commit()
    message = 'The site has been queued for reindexing. You can check on progress by refreshing this page.'
    flash(message)
    return redirect(url_for('manage.indexing'))


# Utilities

def get_manage_data(domain):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    # Get main config
    cursor.execute(sql_select_domains, (domain,))
    result = cursor.fetchone()
    if result['full_indexing_status'] == 'PENDING':
        next_reindex = "Any time now"
    elif result['full_indexing_status_changed'] and result['full_reindex_frequency']:
        next_reindex_datetime = result['full_indexing_status_changed'] + result['full_reindex_frequency']
        next_reindex = next_reindex_datetime.strftime('%d %b %Y, %H:%M%z')
    else: # This shouldn't happen, but just in case
        next_reindex = "Not quite sure"
    # Get domain specific filters
    exclude_paths = []
    exclude_types = []
    cursor.execute(sql_select_filters, (domain,))
    filter_results = cursor.fetchall()
    if filter_results:
        for f in filter_results:
            if f['action'] == 'exclude': # Just handling exclusions for now
                if f['type'] == 'path': exclude_paths.append(f['value'])
                if f['type'] == 'type': exclude_types.append(f['value'])
    return result, next_reindex, exclude_paths, exclude_types

def get_tier_data(domain):
    tier = {}
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_select_tier, (domain,))
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
    cursor.execute(sql_select_subscriptions, (domain,))
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
