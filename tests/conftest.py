import pytest
import psycopg2
import flask
from werkzeug.security import generate_password_hash
import os
from searchmysite import create_app

# Admin user for testing
# It is a non-existant domain, just to create a username that won't conflict with any real domains used for testing
admin_username = "searchmysite.test"
admin_home_page = "https://"+admin_username
admin_password = "searchmysite"
insert_test_admin_user_sql = "INSERT INTO tblIndexedDomains (domain, home_page, password) "\
    "VALUES ((%s), (%s), (%s)); "\
    "INSERT INTO tblPermissions (domain, role) VALUES ((%s), 'admin');"
delete_test_admin_user_sql = "DELETE FROM tblPermissions WHERE domain = (%s); DELETE FROM tblIndexedDomains WHERE domain = (%s);"

# Quick Add test site
quickadd_domain = "example.com"
quickadd_home_page = "http://example.com/"
quickadd_category = "independent-website"
@pytest.fixture
def quickadd_details():
    pytest.quickadd_domain = quickadd_domain
    pytest.quickadd_home_page = quickadd_home_page
    pytest.quickadd_category = quickadd_category

# Verified Add test site
verifiedadd_domain = "searchmysite.net"
verifiedadd_home_page = "https://blog.searchmysite.net/"
verifiedadd_category = "independent-website"
verifiedadd_email = "admin@searchmysite.net"
verifiedadd_password = "searchmysite"
verifiedadd_validation_key = "FSPX5ATCJhuq8BtqCx5aJJgqz1lYFORZsORghYVsiY"
verifiedadd_indexing_page_limit = 10 # Just so indexing doesn't take too long
@pytest.fixture
def verifiedadd_details():
    pytest.verifiedadd_domain = verifiedadd_domain
    pytest.verifiedadd_home_page = verifiedadd_home_page
    pytest.verifiedadd_category = verifiedadd_category
    pytest.verifiedadd_email = verifiedadd_email
    pytest.verifiedadd_password = verifiedadd_password
    pytest.verifiedadd_validation_key = verifiedadd_validation_key
update_validation_key_sql = "UPDATE tblPendingDomains SET validation_key = (%s) WHERE domain = (%s);"
update_indexing_page_limit_sql = "UPDATE tblIndexedDomains SET indexing_page_limit = (%s) WHERE domain = (%s);"

@pytest.fixture(scope='session')
def create_test_admin_user():
    current_app = create_app()
    conn = psycopg2.connect(host=current_app.config['DB_HOST'], dbname=current_app.config['DB_NAME'], user=current_app.config['DB_USER'], password=current_app.config['DB_PASSWORD'])
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(insert_test_admin_user_sql, (admin_username, admin_home_page, generate_password_hash(admin_password), admin_username))
    conn.commit()
    yield (admin_username, admin_password)
    #cursor.execute(delete_test_admin_user_sql, ...)
    cursor.execute(delete_test_admin_user_sql, (admin_username, admin_username))
    conn.commit()

@pytest.fixture(scope='module')
def anon_client():
    current_app = create_app()
    current_app.testing = True
    with current_app.test_client() as anon_client:
        with current_app.app_context():
            yield anon_client

@pytest.fixture(scope='module')
def admin_client(create_test_admin_user):
    current_app = create_app()
    current_app.testing = True
    with current_app.test_client() as admin_client:
        with current_app.app_context():
            response = admin_client.post('/admin/login/', data=dict(
                domain=admin_username,
                password=admin_password
            ), follow_redirects=True)
            yield admin_client

@pytest.fixture(scope='session')
def update_validation_key():
    current_app = create_app()
    conn = psycopg2.connect(host=current_app.config['DB_HOST'], dbname=current_app.config['DB_NAME'], user=current_app.config['DB_USER'], password=current_app.config['DB_PASSWORD'])
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(update_validation_key_sql, (verifiedadd_validation_key, verifiedadd_domain))
    conn.commit()

@pytest.fixture(scope='session')
def update_indexing_page_limit():
    current_app = create_app()
    conn = psycopg2.connect(host=current_app.config['DB_HOST'], dbname=current_app.config['DB_NAME'], user=current_app.config['DB_USER'], password=current_app.config['DB_PASSWORD'])
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(update_indexing_page_limit_sql, (verifiedadd_indexing_page_limit, verifiedadd_domain))
    conn.commit()
