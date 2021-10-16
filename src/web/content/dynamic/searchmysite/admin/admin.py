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

sql_select_quickadd_pending = "SELECT domain, home_page, site_category, date_domain_added "\
    "FROM tblDomains WHERE (validation_method = \'QuickAdd\' OR validation_method = \'SQL\') AND moderator_approved IS NULL "\
    "ORDER BY date_domain_added ASC;"

sql_quickadd_approve = "UPDATE tblDomains SET "\
    "expire_date = now() + '1 year', indexing_type = 'spider/default', indexing_frequency = '28 days', indexing_page_limit = 50, "\
    "indexing_current_status = 'PENDING', indexing_status_last_updated = now(), "\
    "moderator_approved = TRUE, moderator_action_date = now(), moderator_action_user = (%s), indexing_enabled = TRUE "\
    "WHERE domain = (%s);"

sql_quickadd_reject = "UPDATE tblDomains SET "\
    "moderator_approved = FALSE, moderator_action_date = now(), moderator_action_reason = (%s), moderator_action_user = (%s), indexing_enabled = FALSE "\
    "WHERE domain = (%s);"


actions_list = [
{'id':'action1', 'value':'noaction',             'checked':True,  'label':'No action'},
{'id':'action2', 'value':'approve',              'checked':False, 'label':'Approve'},
{'id':'action3', 'value':'reject-notpersonal',   'checked':False, 'label':'Reject - not a personal site'},
{'id':'action4', 'value':'reject-notmaintained', 'checked':False, 'label':'Reject - not actively maintained'},
{'id':'action5', 'value':'reject-shared',        'checked':False, 'label':'Reject - shared domain'},
{'id':'action6', 'value':'reject-other',         'checked':False, 'label':'Reject - reason not listed'},
]

# Setup routes

@bp.route('/review/', methods=('GET', 'POST'))
@login_required
@admin_required
def review():
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_select_quickadd_pending)
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
            review_form.append({'domain':result['domain'], 'home':result['home_page'], 'category':result['site_category'], 'date':result['date_domain_added'], 'actions':actions})
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
                        moderator_action_user = session['logged_in_domain']
                        cursor.execute(sql_quickadd_approve, (moderator_action_user, domain, ))
                        conn.commit()
                    elif action.startswith("reject"):
                        if action == "reject-notpersonal":
                            reason = "Not a personal website"
                        elif action == "reject-notmaintained":
                            reason = "Not actively maintained"
                        elif action == "reject-shared":
                            reason = "Shared domain"
                        else:
                            reason = "Reason not listed"
                        moderator_action_user = session['logged_in_domain']
                        cursor.execute(sql_quickadd_reject, (reason, moderator_action_user, domain, ))
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
