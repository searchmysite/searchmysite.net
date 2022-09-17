import pytest

def test_add_view(anon_client):
    response = anon_client.get('/admin/add/')
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site</title>' in response.data
    assert b'Enter the home page of the site you would like to add' in response.data
    assert b'Confirm what type of site it is' in response.data
    assert b'Select listing tier for your site.' in response.data

def test_review_view_nosubmissions(admin_client):
    response = admin_client.get('/admin/review/')
    assert b'<title>Search My Site - Submission review</title>' in response.data
    assert b'No submissions to review.' in response.data

def test_add_basic_success(anon_client, add_basic_details):
    response = anon_client.post('/admin/add/', data=dict(
        home_page=pytest.add_basic_home_page,
        site_category=pytest.add_basic_category,
        tier=pytest.add_basic_tier
    ), follow_redirects=True)
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site Success</title>' in response.data
    assert b'You have successfully submitted your site.' in response.data

def test_review_view_withsubmissions(admin_client):
    response = admin_client.get('/admin/review/')
    assert b'<title>Search My Site - Submission review</title>' in response.data
    assert b'<button type="submit" class="btn btn-primary">Save changes</button>' in response.data

def test_review_approve(admin_client, add_basic_details):
    response = admin_client.post('/admin/review/', data=dict(
        domain1='{}:approve'.format(pytest.add_basic_domain),
    ), follow_redirects=True)
    assert b'<title>Search My Site - Submission Review Success</title>' in response.data
    assert bytes('<p>Review Success. The following actions have been performed:<ul><li>domain: {}, action: approve</li></ul></p>'.format(pytest.add_basic_domain).encode('utf-8')) in response.data

#def test_manage_view(admin_client):
#    response = admin_client.get('/admin/manage/', follow_redirects=True) # /admin/manage/ redirects to /admin/manage/sitedetails/
#    assert b'<title>Search My Site - Manage My Site</title>' in response.data
#    assert b'Only pages on this domain will be indexed. This your login ID if you use a password.' in response.data
