import pytest
import psycopg2
import flask
from werkzeug.security import generate_password_hash
import os
from searchmysite import create_app
from os import environ

# Admin user for testing
# It is a non-existant domain, just to create a username that won't conflict with any real domains used for testing
admin_username = "searchmysite.test"
admin_home_page = "https://"+admin_username
admin_login_type = "PASSWORD"
admin_password = "searchmysite"
insert_test_admin_user_sql = "INSERT INTO tblDomains (domain, home_page, password, login_type) VALUES ((%s), (%s), (%s), (%s)); "\
    "INSERT INTO tblListingStatus (domain, tier, status) VALUES ((%s), 3, 'ACTIVE'); "\
    "INSERT INTO tblPermissions (domain, role) VALUES ((%s), 'admin');"
delete_test_admin_user_sql = "DELETE FROM tblPermissions WHERE domain = (%s); DELETE FROM tblListingStatus WHERE domain = (%s); DELETE FROM tblDomains WHERE domain = (%s);"

# Basic listing test site
add_basic_domain = "example.com"
add_basic_home_page = "http://example.com/"
add_basic_category = "independent-website"
add_basic_tier = "1"
@pytest.fixture
def add_basic_details():
    pytest.add_basic_domain = add_basic_domain
    pytest.add_basic_home_page = add_basic_home_page
    pytest.add_basic_category = add_basic_category
    pytest.add_basic_tier = add_basic_tier

# Full listing test site
add_full_domain = "searchmysite.net"
add_full_home_page = "https://blog.searchmysite.net/"
add_full_category = "independent-website"
add_full_tier = "3"
add_full_include_public = "True"
add_full_login_type = "PASSWORD"
add_full_email = "admin@searchmysite.net"
add_full_password = "searchmysite"
add_full_validation_key = "FSPX5ATCJhuq8BtqCx5aJJgqz1lYFORZsORghYVsiY"
add_full_indexing_page_limit = 10 # Just so indexing doesn't take too long
@pytest.fixture
def add_full_details():
    pytest.add_full_domain = add_full_domain
    pytest.add_full_home_page = add_full_home_page
    pytest.add_full_category = add_full_category
    pytest.add_full_tier = add_full_tier
    pytest.add_full_include_public = add_full_include_public
    pytest.add_full_login_type = add_full_login_type
    pytest.add_full_email = add_full_email
    pytest.add_full_password = add_full_password
    pytest.add_full_validation_key = add_full_validation_key
update_validation_key_sql = "UPDATE tblValidations SET validation_key = (%s) WHERE domain = (%s);"
update_indexing_page_limit_sql = "UPDATE tblDomains SET indexing_page_limit = (%s) WHERE domain = (%s);"

# Payment testing details
server_url = "http://localhost:8080"
@pytest.fixture
def payment_details():
    pytest.server_url = server_url
    ENABLE_PAYMENT = environ.get('ENABLE_PAYMENT')
    if ENABLE_PAYMENT.lower() == "true" or ENABLE_PAYMENT == "1": 
        ENABLE_PAYMENT = True
    else:
        ENABLE_PAYMENT = False
    pytest.enable_payment = ENABLE_PAYMENT

@pytest.fixture(scope='session')
def create_test_admin_user():
    current_app = create_app()
    conn = psycopg2.connect(host=current_app.config['DB_HOST'], dbname=current_app.config['DB_NAME'], user=current_app.config['DB_USER'], password=current_app.config['DB_PASSWORD'])
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(insert_test_admin_user_sql, (admin_username, admin_home_page, generate_password_hash(admin_password), admin_login_type, admin_username, admin_username))
    conn.commit()
    yield (admin_username, admin_password)
    cursor.execute(delete_test_admin_user_sql, (admin_username, admin_username, admin_username))
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
    cursor.execute(update_validation_key_sql, (add_full_validation_key, add_full_domain))
    conn.commit()

@pytest.fixture(scope='session')
def update_indexing_page_limit():
    current_app = create_app()
    conn = psycopg2.connect(host=current_app.config['DB_HOST'], dbname=current_app.config['DB_NAME'], user=current_app.config['DB_USER'], password=current_app.config['DB_PASSWORD'])
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(update_indexing_page_limit_sql, (add_full_indexing_page_limit, add_full_domain))
    conn.commit()

@pytest.fixture(scope="session")
def browser():
    from selenium import webdriver
    #from chromedriver_py import binary_path
    #driver = webdriver.Chrome(executable_path=binary_path)
    from webdriver_manager.chrome import ChromeDriverManager
    driver = webdriver.Chrome(ChromeDriverManager().install())
    driver.implicitly_wait(10)
    yield driver
    driver.quit()
