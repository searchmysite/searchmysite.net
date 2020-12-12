import pytest

def test_search(anon_client, quickadd_details, verifiedadd_details):
    response = anon_client.get('/search/') # Going to /search/ without a query defaults to a search for everything, i.e. query = * 
    assert response.status_code == 200
    assert b"<title>Search My Site - Results</title>" in response.data
    assert b"results for <em>query = *</em>" in response.data # This is the message shown when there are 1 or more results
    assert b"results found for <em>query = *</em>" not in response.data # This is the message shown when there are no results
    assert b"Search engine for personal websites" not in response.data # This is the text on the home page, i.e. /, rather than /search/
    assert bytes('class="result-link">{}</a>'.format(pytest.quickadd_home_page).encode('utf-8')) in response.data
    assert bytes('class="result-link">{}</a>'.format(pytest.verifiedadd_home_page).encode('utf-8')) in response.data

def test_browse(anon_client):
    response = anon_client.get('/search/browse/')
    assert response.status_code == 200
    assert b"<title>Search My Site - Browse</title>" in response.data
    assert bytes('class="result-link">{}</a>'.format(pytest.quickadd_domain).encode('utf-8')) in response.data
    assert bytes('class="result-link">{}</a>'.format(pytest.verifiedadd_domain).encode('utf-8')) in response.data
