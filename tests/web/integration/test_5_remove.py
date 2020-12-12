import pytest

def test_remove_quickadd(admin_client, quickadd_details):
    response = admin_client.post('/admin/remove/', data=dict(
        domain=pytest.quickadd_domain
    ), follow_redirects=True)
    assert b'<title>Search My Site - Remove Site Success</title>' in response.data
    assert bytes('<p>Removal of {} successful.</p>'.format(pytest.quickadd_domain).encode('utf-8')) in response.data

def test_remove_verifiedadd(admin_client, verifiedadd_details):
    response = admin_client.post('/admin/remove/', data=dict(
        domain=pytest.verifiedadd_domain
    ), follow_redirects=True)
    assert b'<title>Search My Site - Remove Site Success</title>' in response.data
    assert bytes('<p>Removal of {} successful.</p>'.format(pytest.verifiedadd_domain).encode('utf-8')) in response.data
