from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)
from werkzeug.exceptions import abort
from markupsafe import escape
import psycopg2.extras
from os import environ
import json
from searchmysite.admin.auth import login_required, set_login_session, get_login_session
from searchmysite.db import get_db
from searchmysite.util import delete_domain
import config

bp = Blueprint('manage', __name__)

# Initialise variables

selectsql = "SELECT * FROM tblDomains WHERE domain = (%s);"
filterssql = "SELECT * FROM tblIndexingFilters WHERE domain = (%s);"
updateemailsql = "UPDATE tblDomains SET contact_email = (%s) WHERE domain = (%s);"
addexcludesql = "INSERT INTO tblIndexingFilters VALUES ((%s), 'exclude', (%s), (%s));"
deleteexcludesql = "DELETE FROM tblIndexingFilters WHERE domain = (%s) AND action = 'exclude' AND type = (%s) AND VALUE = (%s);"
reindexsql = "UPDATE tblDomains SET indexing_current_status = 'PENDING', indexing_status_last_updated = now() WHERE domain = (%s); "\
    "INSERT INTO tblIndexingLog VALUES ((%s), 'PENDING', now());"

# Setup routes

@bp.route('/manage/')
def manage():
    return redirect(url_for('manage.sitedetails'))

@bp.route('/manage/sitedetails/')
@login_required
def sitedetails():
    (domain, method, is_admin) = get_login_session()
    result, next_reindex, exclude_paths, exclude_types = get_manage_data(domain)
    return render_template('admin/manage-sitedetails.html', result=result, edit=False)

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
            cursor.execute(updateemailsql, (new_email, domain,))
            conn.commit()
        return redirect(url_for('manage.sitedetails'))

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
                cursor.execute(addexcludesql, (domain, "path", save_exclude_path, ))
                conn.commit()
            if save_exclude_type:
                conn = get_db()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute(addexcludesql, (domain, "type", save_exclude_type, ))
                conn.commit()
            return redirect(url_for('manage.indexing'))

@bp.route('/manage/indexing/delete/', methods=('GET', 'POST'))
@login_required
def indexing_delete():
    (domain, method, is_admin) = get_login_session()
    delete_exclude_path = request.form.get("delete_exclude_path")
    delete_exclude_type = request.form.get("delete_exclude_type")
    if delete_exclude_path:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(deleteexcludesql, (domain, "path", delete_exclude_path, ))
        conn.commit()
    if delete_exclude_type:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(deleteexcludesql, (domain, "type", delete_exclude_type, ))
        conn.commit()
    return redirect(url_for('manage.indexing'))

@bp.route('/reindex/')
@login_required
def reindex():
    (domain, method, is_admin) = get_login_session()
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(reindexsql, (domain, domain, ))
    conn.commit()
    message = 'The site has been queued for reindexing. You can check on progress by refreshing this page.'
    flash(message)
    return redirect(url_for('manage.indexing'))

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

def get_manage_data(domain):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    # Get main config
    cursor.execute(selectsql, (domain,))
    result = cursor.fetchone()
    if result['indexing_current_status'] == 'PENDING':
        next_reindex = "Any time now"
    elif result['indexing_status_last_updated'] and result['indexing_frequency']:
        next_reindex_datetime = result['indexing_status_last_updated'] + result['indexing_frequency']
        next_reindex = next_reindex_datetime.strftime('%d %b %Y, %H:%M%z')
    else: # This shouldn't happen, but just in case
        next_reindex = "Not quite sure"
    # Get domain specific filters
    exclude_paths = []
    exclude_types = []
    cursor.execute(filterssql, (domain,))
    filter_results = cursor.fetchall()
    if filter_results:
        for f in filter_results:
            if f['action'] == 'exclude': # Just handling exclusions for now
                if f['type'] == 'path': exclude_paths.append(f['value'])
                if f['type'] == 'type': exclude_types.append(f['value'])
    return result, next_reindex, exclude_paths, exclude_types
