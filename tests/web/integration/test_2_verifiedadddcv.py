import pytest

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

def test_verified_add_dcv_step3_post(anon_client, verifiedadd_details):
    response = anon_client.post('/admin/add/dcv3validate/', follow_redirects=True)
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site Success</title>' in response.data
    assert b'You have successfully validated ownership of your domain.' in response.data

def test_verified_add_dcv_finalise(update_indexing_page_limit):
    return
