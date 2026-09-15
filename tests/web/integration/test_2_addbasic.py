import pytest

def test_review_view_nosubmissions(admin_client):
    response = admin_client.get('/admin/review/')
    assert response.status_code == 200
    assert b'<title>Search My Site - Submission review</title>' in response.data
    assert b'No submissions to review.' in response.data

def test_add_basic_requires_login(anon_client):
    response = anon_client.get('/admin/add/basic/')
    assert response.status_code == 302
    assert '/admin/login/' in response.headers['Location']

def test_login_redirects_back_to_add_basic(anon_client, add_full_details):
    # Uses the credentials of the Full listing submitted in part 1, and checks that
    # after login the user is redirected back to /admin/add/basic/ (the page that
    # originally required login) rather than the default Manage My Site page.
    response = anon_client.post('/admin/login/', data=dict(
        domain=pytest.add_full_domain,
        password=pytest.add_full_password
    ), follow_redirects=True)
    assert response.status_code == 200
    assert response.request.path == '/admin/add/basic/'
    assert b'<title>Search My Site - Add Basic Site</title>' in response.data

def test_add_basic_success(fulluser_client, add_basic_details):
    response = fulluser_client.post('/admin/add/basic/', data=dict(
        home_page=pytest.add_basic_home_page,
        site_category=pytest.add_basic_category,
        tier=pytest.add_basic_tier
    ), follow_redirects=True)
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site Success</title>' in response.data
    assert b'You have successfully submitted your site.' in response.data

def test_review_view_withsubmissions(admin_client):
    response = admin_client.get('/admin/review/')
    assert response.status_code == 200
    assert b'<title>Search My Site - Submission review</title>' in response.data
    assert b'<button type="submit" class="btn btn-primary">Save changes</button>' in response.data

def test_review_approve(admin_client, add_basic_details):
    response = admin_client.post('/admin/review/', data=dict(
        domain1='{}:approve'.format(pytest.add_basic_domain),
    ), follow_redirects=True)
    assert response.status_code == 200
    assert b'<title>Search My Site - Submission Review Success</title>' in response.data
    assert bytes('<p>Review Success. The following actions have been performed:<ul><li>domain: {}, action: approve</li></ul></p>'.format(pytest.add_basic_domain).encode('utf-8')) in response.data
