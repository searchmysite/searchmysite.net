import pytest
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
import time

def test_verified_add_dcv_get(anon_client):
    response = anon_client.get('/admin/add/dcv/')
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site via DCV</title>' in response.data
    assert b'If you don\'t have IndieAuth setup, you can still submit your site' in response.data

def test_verified_add_dcv_step1_get(anon_client, verifiedadd_details):
    response = anon_client.get('/admin/add/dcv1home/')
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site via DCV Step 1</title>' in response.data
    assert b'Enter the home page of your site' in response.data

def test_verified_add_dcv_step1_post(anon_client, verifiedadd_details):
    response = anon_client.post('/admin/add/dcv1home/', data=dict(
        home_page=pytest.verifiedadd_home_page
    ), follow_redirects=True)
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site via DCV Step 2</title>' in response.data
    assert b'The domain is your unique identifier' in response.data

def test_verified_add_dcv_step2_get(anon_client, verifiedadd_details):
    response = anon_client.get('/admin/add/dcv2login/')
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site via DCV Step 2</title>' in response.data
    assert b'The domain is your unique identifier' in response.data

def test_verified_add_dcv_step2_post(anon_client, verifiedadd_details):
    response = anon_client.post('/admin/add/dcv2login/', data=dict(
        site_category=pytest.verifiedadd_category,
        email=pytest.verifiedadd_email,
        password=pytest.verifiedadd_password,
    ), follow_redirects=True)
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site via DCV Step 3</title>' in response.data
    assert b'You must use this key to confirm your ownership of this domain' in response.data

def test_verified_add_dcv_step3_get(anon_client, verifiedadd_details, update_validation_key):
    response = anon_client.get('/admin/add/dcv3validate/')
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site via DCV Step 3</title>' in response.data
    assert b'You must use this key to confirm your ownership of this domain' in response.data
    assert bytes('searchmysite-verification={}'.format(pytest.verifiedadd_validation_key).encode('utf-8')) in response.data

def test_verified_add_dcv_step3_post(anon_client, verifiedadd_details, payment_details):
    response = anon_client.post('/admin/add/dcv3validate/', follow_redirects=True)
    assert response.status_code == 200
    if not pytest.enable_payment:
        assert b'<title>Search My Site - Add Site Success</title>' in response.data
        assert b'You have successfully validated ownership of your domain.' in response.data
    else:
        assert b'<title>Search My Site - Add Site via DCV Step 4</title>' in response.data

def test_verified_add_dcv_step4_get(anon_client, verifiedadd_details, payment_details, browser):
    if not pytest.enable_payment:
        pytest.skip("Payment option not enabled")
    else:
        # We're not using the anon_client session so /admin/add/dcv4payment/ will redirect to /admin/add/dcv1home/
        URL = pytest.server_url + '/admin/add/dcv4payment/'
        browser.get(URL)
        assert 'Search My Site - Add Site via DCV Step 1' in browser.title
        # (Re)submit the home page to get back to /admin/add/dcv4payment/
        home_input = browser.find_element_by_id('home_page')
        home_input.send_keys(pytest.verifiedadd_home_page + Keys.RETURN) # Return also submits
        assert 'Search My Site - Add Site via DCV Step 4' in browser.title
        # Press the Purchase button
        purchase_button = browser.find_element_by_id('submitBtn')
        ActionChains(browser).click(purchase_button).perform()
        time.sleep(4)
        assert 'searchmysite.net' in browser.title
        #assert 'Verified Owner Listing' in browser.response
        # Fill in details
        email_input = browser.find_element_by_id('email')
        email_input.send_keys(pytest.verifiedadd_email)
        card_number_input = browser.find_element_by_id('cardNumber')
        card_number_input.send_keys('4242424242424242')
        card_expiry_input = browser.find_element_by_id('cardExpiry')
        card_expiry_input.send_keys('10/22')
        card_cvc_input = browser.find_element_by_id('cardCvc')
        card_cvc_input.send_keys('123')
        card_billing_name_input = browser.find_element_by_id('billingName')
        card_billing_name_input.send_keys('Michael')
        card_billing_postcode_input = browser.find_element_by_id('billingPostalCode')
        card_billing_postcode_input.send_keys('NW3 1QG' + Keys.RETURN) # Return also submits
        time.sleep(8)
        assert 'Search My Site - Add Site Success' in browser.title
        #assert 'You have successfully validated ownership of your domain.' in browser.response

def test_verified_add_dcv_finalise(update_indexing_page_limit):
    return
