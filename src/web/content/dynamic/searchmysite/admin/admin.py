from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from os import environ
import psycopg2.extras
from searchmysite.admin.auth import login_required, admin_required
from searchmysite.db import get_db
from searchmysite.adminutils import delete_domain, delete_domain_from_solr, get_most_recent_indexing_log_message
import config
import searchmysite.sql


bp = Blueprint('admin', __name__)


actions_list = [
{'id':'action01', 'value':'noaction',             'checked':True,  'label':'No action',                               'reason':''},
{'id':'action02', 'value':'approve',              'checked':False, 'label':'Approve',                                 'reason':''},
{'id':'action03', 'value':'reject-notpersonal',   'checked':False, 'label':'Reject - not a personal site',            'reason':'Not a personal website'},
{'id':'action04', 'value':'reject-notmaintained', 'checked':False, 'label':'Reject - not actively maintained',        'reason':'Not actively maintained'},
{'id':'action05', 'value':'reject-shared',        'checked':False, 'label':'Reject - shared domain',                  'reason':'Shared domain'},
{'id':'action06', 'value':'reject-nocontent',     'checked':False, 'label':'Reject - no content',                     'reason':'No content'},
{'id':'action07', 'value':'reject-notresponding', 'checked':False, 'label':'Reject - not responding',                 'reason':'Site not responding'},
{'id':'action08', 'value':'reject-domainexpired', 'checked':False, 'label':'Reject - domain expired',                 'reason':'Domain expired'},
{'id':'action09', 'value':'reject-robotsblocked', 'checked':False, 'label':'Reject - indexing blocked by robots.txt', 'reason':'Indexing blocked by robots.txt'},
{'id':'action10', 'value':'reject-breach',        'checked':False, 'label':'Reject - breaches Terms of Use',          'reason':'Site breaches Terms of Use'},
{'id':'action11', 'value':'reject-other',         'checked':False, 'label':'Reject - reason not listed',              'reason':'Reason not listed'},
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
            # Construct actions list
            count += 1
            actions = [] 
            name = 'domain'+str(count)
            for action in actions_list:
                action_id = name+action['id']
                action_value = result['domain']+':'+action['value']
                actions.append({'id':action_id, 'name':name, 'value':action_value, 'checked':action['checked'], 'label':action['label']})
            # Determine status of last index (or NEW if no last index)
            status = get_most_recent_indexing_log_message(result['domain'])
            # Append to review_form list of dicts
            review_form.append({'domain':result['domain'], 'home':result['home_page'], 'category':result['category'], 'date':result['domain_first_submitted'].strftime('%d %b %Y, %H:%M'), 'status':status, 'actions':actions})
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
                        reason = next((a['reason'] for a in actions_list if a['value'] == action), 'Reason not listed') # Use the reason for value matching action, default to 'Reason not listed'
                        moderator = session['logged_in_domain']
                        cursor.execute(searchmysite.sql.sql_update_basic_reject, (domain, moderator, reason, domain))
                        conn.commit()
                        # Also need to delete any documents from Solr, in case the domain had been previously indexed, to prevent stale documents in the index
                        delete_domain_from_solr(domain)
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
