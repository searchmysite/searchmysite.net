from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from os import environ
import psycopg2.extras
from searchmysite.admin.auth import login_required, admin_required
from searchmysite.db import get_db
from searchmysite.util import delete_domain
import config

bp = Blueprint('admin', __name__)

# SQL 

sql_select = 'SELECT home_page FROM tblDomains WHERE domain = (%s);'

sql_select_basic_pending = "SELECT d.domain, d.home_page, d.category, d.domain_first_submitted FROM tblDomains d "\
    "INNER JOIN tblListingStatus l ON d.domain = l.domain "\
    "WHERE l.status = 'PENDING' AND l.tier = 1 AND l.pending_state = 'MODERATOR_REVIEW' "\
    "ORDER BY l.listing_end DESC, l.tier ASC;"

sql_update_basic_approved = "UPDATE tblListingStatus "\
    "SET status = 'ACTIVE', status_changed = NOW(), pending_state = NULL, pending_state_changed = NOW(), listing_start = NOW(), listing_end = NOW() + (SELECT listing_duration FROM tblTiers WHERE tier = 1) "\
    "WHERE domain = (%s) AND status = 'PENDING' AND tier = 1 AND pending_state = 'MODERATOR_REVIEW'; "\
    "UPDATE tblDomains SET "\
    "moderator_approved = TRUE, "\
    "moderator = (%s), "\
    "full_reindex_frequency = tblTiers.default_full_reindex_frequency, "\
    "part_reindex_frequency = tblTiers.default_part_reindex_frequency, "\
    "indexing_page_limit = tblTiers.default_indexing_page_limit, "\
    "on_demand_reindexing = tblTiers.default_on_demand_reindexing, "\
    "api_enabled = tblTiers.default_api_enabled, "\
    "indexing_enabled = TRUE, "\
    "full_indexing_status = 'PENDING', "\
    "full_indexing_status_changed = NOW() "\
    "FROM tblTiers WHERE tblTiers.tier = 1 and tblDomains.domain = (%s);"

sql_update_basic_reject = "UPDATE tblListingStatus "\
    "SET status = 'DISABLED', status_changed = NOW(), pending_state = NULL, pending_state_changed = NOW() "\
    "WHERE domain = (%s) AND tier = 1; "\
    "UPDATE tblDomains SET "\
    "moderator_approved = FALSE, "\
    "moderator = (%s), "\
    "moderator_action_reason = (%s), "\
    "moderator_action_changed = NOW() "\
    "WHERE domain = (%s);"


actions_list = [
{'id':'action1', 'value':'noaction',             'checked':True,  'label':'No action'},
{'id':'action2', 'value':'approve',              'checked':False, 'label':'Approve'},
{'id':'action3', 'value':'reject-notpersonal',   'checked':False, 'label':'Reject - not a personal site'},
{'id':'action4', 'value':'reject-notmaintained', 'checked':False, 'label':'Reject - not actively maintained'},
{'id':'action5', 'value':'reject-shared',        'checked':False, 'label':'Reject - shared domain'},
{'id':'action6', 'value':'reject-nocontent',     'checked':False, 'label':'Reject - no content'},
{'id':'action8', 'value':'reject-other',         'checked':False, 'label':'Reject - reason not listed'},
]


# Setup routes

@bp.route('/review/', methods=('GET', 'POST'))
@login_required
@admin_required
def review():
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_select_basic_pending)
    results = cursor.fetchall()
    if request.method == 'GET':
        review_form = [] # Form will be constructed from a list of dicts, where the dict will have domain, home, category, date and actions values, and actions will be a list
        count = 0
        for result in results:
            count += 1
            actions = [] 
            name = 'domain'+str(count)
            for action in actions_list:
                action_id = name+action['id']
                action_value = result['domain']+':'+action['value']
                actions.append({'id':action_id, 'name':name, 'value':action_value, 'checked':action['checked'], 'label':action['label']})
            review_form.append({'domain':result['domain'], 'home':result['home_page'], 'category':result['category'], 'date':result['domain_first_submitted'], 'actions':actions})
        return render_template('admin/review.html', results=results, review_form=review_form)
    else: # i.e. if POST 
        if results:
            message = '<p>Review Success. The following actions have been performed:<ul>'
            count = 0
            for result in results:
                count += 1
                name = 'domain'+str(count)
                value = request.form.get(name) # actions are in the form domain:action, with action one of the value fields in the actions_list
                if value:
                    domainaction = value.split(':')
                    domain = domainaction[0]
                    action = domainaction[1]
                    message += '<li>domain: {}, action: {}</li>'.format(domain, action)                    
                    if action == "approve":
                        moderator = session['logged_in_domain']
                        cursor.execute(sql_update_basic_approved, (domain, moderator, domain, ))
                        conn.commit()
                    elif action.startswith("reject"):
                        if action == "reject-notpersonal":
                            reason = "Not a personal website"
                        elif action == "reject-notmaintained":
                            reason = "Not actively maintained"
                        elif action == "reject-shared":
                            reason = "Shared domain"
                        elif action == "reject-nocontent":
                            reason = "No content"
                        else:
                            reason = "Reason not listed"
                        moderator = session['logged_in_domain']
                        cursor.execute(sql_update_basic_reject, (domain, moderator, reason, domain))
                        conn.commit()
            message += '</ul></p>' 
            return render_template('admin/success.html', title="Submission Review Success", message=message)
        else:
            return render_template('admin/review.html')

@bp.route('/remove/', methods=('GET', 'POST'))
@login_required
@admin_required
def remove():
    if request.method == 'GET':
        return render_template('admin/remove.html')
    else: # i.e. if POST
        domain = request.form.get('domain')
        # Check if domain exists first
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_select, (domain, ))
        results = cursor.fetchone()
        if results:
            delete_domain(domain)
            message = '<p>Removal of {} successful.</p>'.format(domain) 
            return render_template('admin/success.html', title="Remove Site Success", message=message)
        else:
            flash('Unable to delete: domain {} not found'.format(domain))
            return render_template('admin/remove.html')
