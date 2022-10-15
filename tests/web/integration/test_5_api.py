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
    json_params = json.dumps(params)
    json_response = json.loads(response.data)
    assert response.status_code == 200
    assert json.dumps(json_response['params']) == json_params

