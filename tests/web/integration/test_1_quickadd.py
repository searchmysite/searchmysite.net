import pytest

def test_quick_add_view(anon_client):
    response = anon_client.get('/admin/add/quick/')
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site</title>' in response.data
    assert b'Enter the home page of the site you would like to see indexed.' in response.data

def test_review_view_nosubmissions(admin_client):
    response = admin_client.get('/admin/review/')
    assert b'<title>Search My Site - Submission review</title>' in response.data
    assert b'No submissions to review.' in response.data

def test_quick_add_submit_success(anon_client, quickadd_details):
    response = anon_client.post('/admin/add/quick/', data=dict(
        home_page=pytest.quickadd_home_page,
        site_category=pytest.quickadd_category
    ), follow_redirects=True)
    assert response.status_code == 200
    assert b'<title>Search My Site - Add Site Success</title>' in response.data
    assert b'You have successfully submitted your site.' in response.data
# Other possible Quick Add responses:
# Domain has already been submitted and is being indexed:
# <title>Search My Site - Add Site</title>
# <div class="alert alert-warning" role="alert">Domain michael-lewis.com is already being indexed
# Domain has already been submitted but has been rejected:
# <title>Search My Site - Add Site</title>
# <div class="alert alert-warning" role="alert">Domain pylons.org with a home page at http://pylons.org has previously been submitted but rejected
# Domain has already been submitted but is pending review/verification:
# <title>Search My Site - Add Site</title>
# <div class="alert alert-warning" role="alert">Domain michael-lewis.com with a home page at http://michael-lewis.com/ has already been submitted and is pending review/verification.</div>

def test_review_view_withsubmissions(admin_client):
    response = admin_client.get('/admin/review/')
    assert b'<title>Search My Site - Submission review</title>' in response.data
    assert b'<button type="submit" class="btn btn-primary">Save changes</button>' in response.data

def test_review_approve(admin_client, quickadd_details):
    response = admin_client.post('/admin/review/', data=dict(
        domain1='{}:approve'.format(pytest.quickadd_domain),
    ), follow_redirects=True)
    assert b'<title>Search My Site - Submission Review Success</title>' in response.data
    assert bytes('<p>Review Success. The following actions have been performed:<ul><li>domain: {}, action: approve</li></ul></p>'.format(pytest.quickadd_domain).encode('utf-8')) in response.data

#def test_manage_view(admin_client):
#    response = admin_client.get('/admin/manage/', follow_redirects=True) # /admin/manage/ redirects to /admin/manage/sitedetails/
#    assert b'<title>Search My Site - Manage My Site</title>' in response.data
#    assert b'Only pages on this domain will be indexed. This your login ID if you use a password.' in response.data
