import pytest

def test_remove_add_basic(admin_client, add_basic_details):
    response = admin_client.post('/admin/remove/', data=dict(
        domain=pytest.add_basic_domain
    ), follow_redirects=True)
    assert b'<title>Search My Site - Remove Site Success</title>' in response.data
    assert bytes('<p>Removal of {} successful.</p>'.format(pytest.add_basic_domain).encode('utf-8')) in response.data

def test_remove_add_full(admin_client, add_full_details):
    response = admin_client.post('/admin/remove/', data=dict(
        domain=pytest.add_full_domain
    ), follow_redirects=True)
    assert b'<title>Search My Site - Remove Site Success</title>' in response.data
    assert bytes('<p>Removal of {} successful.</p>'.format(pytest.add_full_domain).encode('utf-8')) in response.data
