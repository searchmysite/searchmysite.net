import pytest

def test_api_basic(anon_client, add_basic_details):
    response = anon_client.get('/api/v1/search/' + pytest.add_basic_domain + '?q=*')
    assert response.status_code == 400
    assert b"does not have the API enabled" in response.data # Full response {"message": "Domain example.com does not have the API enabled"}

def test_api_full(anon_client, add_full_details):
    response = anon_client.get('/api/v1/search/' + pytest.add_full_domain + '?q=*')
    assert response.status_code == 200
    assert b"\"results\":" in response.data

