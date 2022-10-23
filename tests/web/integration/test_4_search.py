import pytest

def test_search(anon_client, add_basic_details, add_full_details):
    response = anon_client.get('/search/') # Going to /search/ without a query defaults to a search for everything, i.e. query = * 
    assert response.status_code == 200
    assert b"<title>Search My Site - Search Results</title>" in response.data
    assert b" results" in response.data # This is the message shown when there are 1 or more results
    assert b"No results found for " not in response.data # This is the message shown when there are no results
    assert b"searchmysite.net is an open source search engine and search as a service" not in response.data # This is the text on the home page, i.e. /, rather than /search/
    assert bytes('class="result-link">{}</a>'.format(pytest.add_basic_home_page).encode('utf-8')) in response.data
    assert bytes('class="result-link">{}</a>'.format(pytest.add_full_home_page).encode('utf-8')) in response.data

def test_browse(anon_client):
    response = anon_client.get('/search/browse/')
    assert response.status_code == 200
    assert b"<title>Search My Site - Browse Sites</title>" in response.data
    assert bytes('class="result-link">{}</a>'.format(pytest.add_basic_domain).encode('utf-8')) in response.data
    assert bytes('class="result-link">{}</a>'.format(pytest.add_full_domain).encode('utf-8')) in response.data
