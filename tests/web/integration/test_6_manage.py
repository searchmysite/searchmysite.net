import pytest

# Tests for the "Include in public search" toggle on the Manage Site / Indexing page.
# A site owner can now change this setting themselves (previously it could only be set at
# listing time or by contacting support). Changing it updates the domain in the database
# and queues a reindex, because the value is stored in Solr at index time and the public
# search (along with Browse, Newest and Random) filters on it.
#
# These run after a Full listing has been submitted and indexed (parts 1-5), so the owner
# can log in (fulluser_client). A Full listing defaults to "Include in public search" = True.
# The last test restores the value to True so it does not affect the removal step.

def _flat(data):
    # Collapse all whitespace so assertions are robust to HTML line-wrapping
    return b" ".join(data.split())

def test_manage_indexing_shows_public_search_radio(fulluser_client, add_full_details):
    response = fulluser_client.get('/admin/manage/indexing/')
    assert response.status_code == 200
    data = _flat(response.data)
    # The boolean field is rendered as two radio buttons
    assert b'id="include_in_public_search_true"' in data
    assert b'id="include_in_public_search_false"' in data
    # A Full listing defaults to include in public search, so the "Yes" radio is checked
    assert b'id="include_in_public_search_true" value="True" checked' in data

def test_manage_indexing_no_change_does_not_reindex(fulluser_client, add_full_details):
    # Submitting the current value (True) changes nothing and does not queue a reindex
    response = fulluser_client.post('/admin/manage/indexing/', data={
        'edited-field': 'include_in_public_search',
        'include_in_public_search': 'True'
    })
    assert response.status_code == 200
    data = _flat(response.data)
    assert b'queued for reindexing' not in data
    assert b'id="include_in_public_search_true" value="True" checked' in data

def test_manage_indexing_toggle_off(fulluser_client, add_full_details):
    response = fulluser_client.post('/admin/manage/indexing/', data={
        'edited-field': 'include_in_public_search',
        'include_in_public_search': 'False'
    })
    assert response.status_code == 200
    data = _flat(response.data)
    # The value changed, so a reindex is queued and a message is shown
    assert b'queued for reindexing' in data
    assert b'id="include_in_public_search_false" value="False" checked' in data

def test_manage_indexing_toggle_back_on(fulluser_client, add_full_details):
    # Restore the default (True) so later parts are unaffected
    response = fulluser_client.post('/admin/manage/indexing/', data={
        'edited-field': 'include_in_public_search',
        'include_in_public_search': 'True'
    })
    assert response.status_code == 200
    data = _flat(response.data)
    assert b'queued for reindexing' in data
    assert b'id="include_in_public_search_true" value="True" checked' in data
