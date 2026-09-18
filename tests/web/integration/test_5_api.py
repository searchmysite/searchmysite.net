import pytest
import json

def test_api_basic(anon_client, add_basic_details):
    response = anon_client.get('/api/v1/search/' + pytest.add_basic_domain + '?q=*')
    assert response.status_code == 400
    assert b"does not have the API enabled" in response.data # Full response {"message": "Domain example.com does not have the API enabled"}

def test_api_full(anon_client, add_full_details):
    response = anon_client.get('/api/v1/search/' + pytest.add_full_domain + '?q=*')
    assert response.status_code == 200
    assert b"\"results\":" in response.data # check that there are results
    assert json.loads(response.data) # check that it is valid json

def test_api_full_and_params(anon_client, add_full_details):
    q = 'search'
    page = 2
    resultsperpage = 2
    response = anon_client.get('/api/v1/search/{}?q={}&page={}&resultsperpage={}'.format(pytest.add_full_domain, q, page, resultsperpage))
    params = {'q': q, 'page': page, 'resultsperpage': resultsperpage}
    json_response = json.loads(response.data)
    assert response.status_code == 200
    assert json.dumps(json_response['params'], sort_keys=True) == json.dumps(params, sort_keys=True)

def test_status_basic(anon_client, add_basic_details):
    response = anon_client.get('/api/v1/status/' + pytest.add_basic_domain)
    json_response = json.loads(response.data)
    assert response.status_code == 200
    assert json_response['domain'] == pytest.add_basic_domain
    assert json_response['tier'] == 1
    assert json_response['api_enabled'] is False
    assert 'max-age=3600' in response.headers['Cache-Control']

def test_status_full(anon_client, add_full_details):
    response = anon_client.get('/api/v1/status/' + pytest.add_full_domain)
    json_response = json.loads(response.data)
    assert response.status_code == 200
    assert json_response['domain'] == pytest.add_full_domain
    assert json_response['tier'] == 3
    assert json_response['api_enabled'] is True

def test_status_unknown(anon_client, add_basic_details):
    response = anon_client.get('/api/v1/status/not-a-real-domain-xyz.com')
    assert response.status_code == 404
    assert b"not found" in response.data # Full response {"message": "Domain not-a-real-domain-xyz.com not found"}

