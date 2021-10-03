import json
from indexer.util import convert_datetime_to_utc_date

file = "cirrussearch/unprocessed/enwikiaaaaaaaaaa"
linkroot = "https://en.wikipedia.org/wiki/"

# File is in the format
"""
{
    "index": {
        "_type": "page",
        "_id": "..."
    }
}
{
    "template": [
        ...
    ],
    ...
    "title": "...",
    "text": "...",
    ...
}
{
    "index": {
        "_type": "page",
        "_id": "..."
    }
}
{
    "template": [
        ...
    ],
    ...
    "title": "...",
    "text": "...",
    ...
}
"""
# This isn't a valid JSON file because it contains multiple JSON objects
# rather than a single list of objects [{}, {}...] or single object.
# So we're going to create a list of objects, where each object is 
# the index object merged with the subsequent non-index object(s), i.e.
# [
# {'index': {...}, 'template': [...], ... },
# {'index': {...}, 'template': [...], ... }
# ]
inputPages = []
with open(file) as f:
    for jsonObj in f:
        j = json.loads(jsonObj)
        if "index" in j:
            page = dict()
            page.update(j)
            inputPages.append(page)
        else:
            page = inputPages[-1]
            page.update(j)

# Mapping between searchmysite.net Solr schema and wikipedia cirrussearch dump:
# id -> same as url
# url -> inputPage["title"] transformed accordingly (see comments below)
# domain -> always wikipedia.org
# is_home -> always False unless title="Main Page"
# title -> inputPage["title"]
# author -> n/a
# description -> n/a
# tags -> n/a
# body -> likely to be deprecated so don't populate
# content -> inputPage["text"]
# page_type -> appears to be "website" for all pages so no real value in adding
# page_last_modified -> inputPage["timestamp"] . Might already be in Solr's DateTimeFormatter.ISO_INSTANT format, i.e. YYYY-MM-DDThh:mm:ssZ, e.g. 2021-07-02T18:37:57Z
# published_date -> n/a
# indexed_date -> convert_datetime_to_utc_date(datetime.datetime.now())
# date_domain_added -> only set if is_home = True. Could be hardcoded for now, but should be "SELECT date_domain_added FROM tblIndexedDomains WHERE domain = 'wikipedia.org';"
# site_category -> always "independent-website"
# site_last_modified -> TBC, perhaps use the timestamp from the import (same value for all pages in a site)
# owner_verified -> assumed to be False for now (but should in future could be a database lookup to confirm)
# contains_adverts -> assume False
# api_enabled -> only set if is_home = True. assume False
# language -> inputPage["language"]
# language_primary -> inputPage["language"][:2]
# indexed_inlinks -> it would be the query http://localhost:8983/solr/content/select?q=*%3A*&fq=indexed_outlinks%3A*wikipedia.org*&fl=url,indexed_outlinks&rows=10000 
#                    but wikipedia.org needs to be added to the SELECT DISTINCT domain FROM tblIndexedDomains; to appear in other pages indexed_outlinks first
# indexed_inlinks_count -> 
# indexed_inlink_domains -> 
# indexed_inlink_domains_count ->
# indexed_outlinks -> get domains_for_indexed_links, and check all external_link for a link on a domain in domains_for_indexed_links

outputPages = []
for inputPage in inputPages:
    page = dict()
    # Converting titles to urls:
    # From https://en.wikipedia.org/wiki/Help:URL
    # "If constructing URLs for Wikipedia pages, remember to convert spaces into underscores, and to percent-code special characters where necessary"
    # Examples
    # Preludes (Rachmaninoff) -> https://en.wikipedia.org/wiki/Preludes_(Rachmaninoff)
    # The Vampyr: A Soap Opera -> https://en.wikipedia.org/wiki/The_Vampyr:_A_Soap_Opera
    # Meisterstück -> https://en.wikipedia.org/wiki/Meisterst%C3%BCck
    # Princess of Wales's Stakes -> https://en.wikipedia.org/wiki/Princess_of_Wales%27s_Stakes (conversely outgoing_link is e.g. Princess_of_Wales's_Stakes)
    page['id'] = "https://en.wikipedia.org/wiki/" + inputPage["title"].replace(" ", "_")
    page['url'] = page['id']
    page['domain'] = "wikipedia.org"
    if inputPage["title"] == 'Main Page':
        page['is_home'] = True
        # date_domain_added -> only set if is_home = True. Could be hardcoded for now, but should be "SELECT date_domain_added FROM tblIndexedDomains WHERE domain = 'wikipedia.org';"
        page[' api_enabled'] = False
    else:
        page['is_home'] = False
    page['title'] = inputPage["title"]
    #page['content'] = inputPage["text"]
    page['page_last_modified'] = inputPage["timestamp"]
    page['indexed_date'] = convert_datetime_to_utc_date(datetime.datetime.now())
    page['language'] = inputPage["language"]
    page['language_primary'] = inputPage["language"][:2]
    outputPages.append(page)

print(outputPages)
