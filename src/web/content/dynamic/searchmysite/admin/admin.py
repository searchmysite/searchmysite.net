from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from os import environ
import psycopg2.extras
from searchmysite.admin.auth import login_required, admin_required
from searchmysite.db import get_db
from searchmysite.adminutils import delete_domain
import config
import searchmysite.sql


bp = Blueprint('admin', __name__)


actions_list = [
{'id':'action1', 'value':'noaction',             'checked':True,  'label':'No action'},
{'id':'action2', 'value':'approve',              'checked':False, 'label':'Approve'},
{'id':'action3', 'value':'reject-notpersonal',   'checked':False, 'label':'Reject - not a personal site'},
{'id':'action4', 'value':'reject-notmaintained', 'checked':False, 'label':'Reject - not actively maintained'},
{'id':'action5', 'value':'reject-shared',        'checked':False, 'label':'Reject - shared domain'},
{'id':'action6', 'value':'reject-nocontent',     'checked':False, 'label':'Reject - no content'},
{'id':'action7', 'value':'reject-notresponding', 'checked':False, 'label':'Reject - not responding'},
{'id':'action8', 'value':'reject-breach',        'checked':False, 'label':'Reject - breaches Terms of Use'},
{'id':'action9', 'value':'reject-other',         'checked':False, 'label':'Reject - reason not listed'},
]


# Setup routes

@bp.route('/review/', methods=('GET', 'POST'))
@login_required
@admin_required
def review():
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(searchmysite.sql.sql_select_basic_pending)
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
                        cursor.execute(searchmysite.sql.sql_update_basic_approved, (domain, moderator, domain, ))
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
                        elif action == "reject-notresponding":
                            reason = "Site not responding"
                        elif action == "reject-breach":
                            reason = "Site breaches Terms of Use"
                        else:
                            reason = "Reason not listed"
                        moderator = session['logged_in_domain']
                        cursor.execute(searchmysite.sql.sql_update_basic_reject, (domain, moderator, reason, domain))
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
        cursor.execute(searchmysite.sql.sql_select_home_page, (domain, ))
        results = cursor.fetchone()
        if results:
            delete_domain(domain)
            message = '<p>Removal of {} successful.</p>'.format(domain) 
            return render_template('admin/success.html', title="Remove Site Success", message=message)
        else:
            flash('Unable to delete: domain {} not found'.format(domain))
            return render_template('admin/remove.html')
