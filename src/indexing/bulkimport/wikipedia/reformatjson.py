import json
from datetime import datetime
import sys
import os

# Change the sys path so we can import utilities common to both the src/indexer/bulkimport and src/indexer/indexer 
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from common import config
from common import utils

# Get command line parameters, i.e. file and language
try:
    input_file = sys.argv[1] 
except IndexError:
    print("Please specify a file to process and optional language, e.g. python reformatjson.py cirrussearch/en/enwiki-aaaaaa en")
    sys.exit()
try:
    lang = sys.argv[2]
except IndexError:
    lang = "en"

# Get list of indexed domains and list of domains which allow subdomains 
domains = utils.get_all_domains()
domains_allowing_subdomains = utils.get_domains_allowing_subdomains()

# Get indexed outlinks
domain = "wikipedia.org"
all_indexed_inlinks = utils.get_all_indexed_inlinks_for_domain(domain)

# Other variables
output_file = input_file # Overwrite existing file when done to save disk space
#output_file = input_file + ".json" # Create new output file, useful for dev testing
linkroot = "https://" + lang + "." + domain + "/wiki/"


# Step 1: Make valid JSON
# input_file is in the format
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
input_pages = []
with open(input_file) as infile:
    for jsonObj in infile:
        j = json.loads(jsonObj)
        if "index" in j:
            page = dict()
            page.update(j)
            input_pages.append(page)
        else:
            page = input_pages[-1]
            page.update(j)


# Step 2: Create new JSON
output_pages = []
for input_page in input_pages:
    page = dict()
    # Converting titles to urls:
    # From https://en.wikipedia.org/wiki/Help:URL
    # "If constructing URLs for Wikipedia pages, remember to convert spaces into underscores, and to percent-code special characters where necessary"
    # Examples
    # Preludes (Rachmaninoff) -> https://en.wikipedia.org/wiki/Preludes_(Rachmaninoff)
    # The Vampyr: A Soap Opera -> https://en.wikipedia.org/wiki/The_Vampyr:_A_Soap_Opera
    # Meisterstück -> https://en.wikipedia.org/wiki/Meisterst%C3%BCck
    # Princess of Wales's Stakes -> https://en.wikipedia.org/wiki/Princess_of_Wales%27s_Stakes (although outgoing_link is e.g. Princess_of_Wales's_Stakes)
    if 'title' in input_page: # Don't do any of this if there's not a title
        page['id'] = linkroot + input_page["title"].replace(" ", "_")
        page['url'] = page['id']
        page['domain'] = domain
        if input_page["title"] == 'Main Page':
            page['is_home'] = True
            # Original wikipedia.org submission date was "2020-11-25T09:43:50.344Z"
            # That is almost the correct format for Solr - just need to remove the .344
            # Hardcoding date_domain_added for now, but should be "SELECT date_domain_added FROM tblIndexedDomains WHERE domain = 'wikipedia.org';" in case it changes
            page['date_domain_added'] = '2020-11-25T09:43:50Z'
            page['api_enabled'] = False
        else:
            page['is_home'] = False
        page['title'] = input_page["title"]
        # author, description & tags -> n/a. body -> likely to be deprecated so don't populate
        page['content'] = input_page["text"]
        # page_type -> appears to be "website" for all pages so no real value in adding
        page['page_last_modified'] = input_page["timestamp"] # Looks like it is already in Solr's DateTimeFormatter.ISO_INSTANT format, i.e. YYYY-MM-DDThh:mm:ssZ, e.g. 2021-07-02T18:37:57Z
        # published_date -> n/a
        page['indexed_date'] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        page['site_category'] = "independent-website"
        #page['site_last_modified'] = "" # TBC, but not currently populated elsewhere. Perhaps use the timestamp from the import (same value for all pages in a site)
        page['owner_verified'] = False # assumed to be False for now (but should in future could be a database lookup to confirm)
        page['contains_adverts'] = False # contains_adverts -> assume False
        if 'language' in input_page:
            page['language'] = input_page["language"]
            page['language_primary'] = input_page["language"][:2]
        # Populate indexed_inlinks, indexed_inlinks_count, indexed_inlink_domains and indexed_inlink_domains_count
        # i.e. the links and domains with links to this page 
        if page['url'] in all_indexed_inlinks:
            page['indexed_inlinks'] = all_indexed_inlinks[page['url']]
        if 'indexed_inlinks' in page and len(page['indexed_inlinks']) > 0:
            page['indexed_inlinks_count'] = len(page['indexed_inlinks'])
        indexed_inlink_domains = []
        if 'indexed_inlinks' in page:
            for indexed_inlink in page['indexed_inlinks']:
                indexed_inlink_domain = utils.extract_domain_from_url(indexed_inlink, domains_allowing_subdomains)
                if indexed_inlink_domain not in indexed_inlink_domains:
                    indexed_inlink_domains.append(indexed_inlink_domain)
        page['indexed_inlink_domains'] = indexed_inlink_domains
        if len(indexed_inlink_domains) > 0:
            page['indexed_inlink_domains_count'] = len(indexed_inlink_domains)
        # Populate the indexed_outlinks, i.e. pages on other domains within this index to which this page links
        # Note that the mechanism here isn't bulletproof - it just looks for the domain string anywhere rather than between the "//" and first "/"
        # But given it will be run 10s of millions of times for potentially 100s of links on potentially 1000s of domains
        # we want it to be fairly fast 
        indexed_outlinks = []
        if domains and "external_link" in input_page:
            links = input_page["external_link"]
            for link in links:
                if any(domain in link for domain in domains): 
                    indexed_outlinks.append(link)
        page['indexed_outlinks'] = indexed_outlinks
        output_pages.append(page)
    else:
        print("Page id {} from file {} was not imported due to missing title: ".format(input_page['index']['_id'], input_file))


# Step 3: Save new JSON
with open(output_file, 'w') as outfile:
    json.dump(output_pages, outfile)
