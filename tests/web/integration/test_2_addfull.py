import pytest
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
import time

def test_full_usernamepassword_step0_post(anon_client, add_full_details):
    response = anon_client.post('/admin/add/', data=dict(
        home_page=pytest.add_full_home_page,
        site_category=pytest.add_full_category,
        tier=pytest.add_full_tier
    ), follow_redirects=True)
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site Step 1</title>' in response.data

def test_full_usernamepassword_step1_get(anon_client, add_full_details):
    response = anon_client.get('/admin/add/step1/')
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site Step 1</title>' in response.data
    assert b'Include in public search' in response.data
    assert b'Login and domain ownership validation method' in response.data

def test_full_usernamepassword_step1_post(anon_client, add_full_details):
    response = anon_client.post('/admin/add/step1/', data=dict(
        include_public=pytest.add_full_include_public,
        login_type=pytest.add_full_login_type
    ), follow_redirects=True)
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site Step 2</title>' in response.data

def test_full_usernamepassword_step2_get(anon_client, add_full_details):
    response = anon_client.get('/admin/add/step2/')
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site Step 2</title>' in response.data
    assert b'Admin email' in response.data
    assert b'Password' in response.data

def test_full_usernamepassword_step2_post(anon_client, add_full_details):
    response = anon_client.post('/admin/add/step2/', data=dict(
        email=pytest.add_full_email,
        password=pytest.add_full_password
    ), follow_redirects=True)
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site Step 3</title>' in response.data

def test_full_usernamepassword_step3_get(anon_client, add_full_details, update_validation_key):
    response = anon_client.get('/admin/add/step3/')
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site Step 3</title>' in response.data
    assert b'You must use this key to confirm your ownership of this domain' in response.data
    assert bytes('searchmysite-verification={}'.format(pytest.add_full_validation_key).encode('utf-8')) in response.data

def test_full_usernamepassword_step3_post(anon_client, add_full_details, payment_details):
    response = anon_client.post('/admin/add/step3/', follow_redirects=True)
    assert response.status_code == 200
    if not pytest.enable_payment:
        assert b'<title>Search My Site - Add Site Success</title>' in response.data
        assert b'You have successfully validated ownership of your domain.' in response.data
    else:
        assert b'<title>Search My Site - Add Site Step 4</title>' in response.data

def test_full_usernamepassword_get(anon_client, add_full_details, payment_details, browser):
    if not pytest.enable_payment:
        pytest.skip("Payment option not enabled")
    else:
        # We're not using the anon_client session so /admin/add/step4/ will redirect to /admin/add/
        URL = pytest.server_url + '/admin/add/step4/'
        browser.get(URL)
        assert 'Search My Site - Add Site' in browser.title
        # (Re)submit the home page to get back to /admin/add/step4/
        browser.find_element(By.CSS_SELECTOR, "input[type='radio'][value='independent-website']").click() # site_category
        browser.find_element(By.CSS_SELECTOR, "input[type='radio'][value='3']").click() # tier
        home_input = browser.find_element(By.ID, 'home_page')
        home_input.send_keys(pytest.add_full_home_page)
        add_site_button = browser.find_element(By.ID, 'add-site')
        ActionChains(browser).click(add_site_button).perform()
        time.sleep(2)
        assert 'Search My Site - Add Site Step 4' in browser.title
        # Press the Purchase button
        purchase_button = browser.find_element(By.ID, 'submitBtn')
        ActionChains(browser).click(purchase_button).perform()
        time.sleep(4)
        #assert 'searchmysite.net' in browser.title
        #assert 'Verified Owner Listing' in browser.response
        assert 'Stripe' in browser.page_source
        # Fill in details
        email_input = browser.find_element(By.ID, 'email')
        email_input.send_keys(pytest.add_full_email)
        card_number_input = browser.find_element(By.ID, 'cardNumber')
        card_number_input.send_keys('4242424242424242')
        card_expiry_input = browser.find_element(By.ID, 'cardExpiry')
        card_expiry_input.send_keys('10/24')
        card_cvc_input = browser.find_element(By.ID, 'cardCvc')
        card_cvc_input.send_keys('123')
        card_billing_name_input = browser.find_element(By.ID, 'billingName')
        card_billing_name_input.send_keys('Michael')
        card_billing_postcode_input = browser.find_element(By.ID, 'billingPostalCode')
        card_billing_postcode_input.send_keys('NW3 1QG' + Keys.RETURN) # Return also submits
        time.sleep(6) # Give it time to submit and follow redirects
        assert 'Search My Site - Add Site Success' in browser.title
        #assert 'You have successfully submitted your site.' in browser.response

def test_full_usernamepassword_finalise(update_indexing_page_limit):
    return
