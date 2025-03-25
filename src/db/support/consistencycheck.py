#!/usr/bin/env python3
import sys
import os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(SCRIPT_DIR))
from common.utils import convert_list_of_dicts_to_list_of_domains, select_indexed_domains, get_solr_domains_with_or_without_home, get_solr_domains_with_a_home_page, get_indexing_log_message

database_domains = convert_list_of_dicts_to_list_of_domains(select_indexed_domains())
solr_domains_with_or_without_home = get_solr_domains_with_or_without_home()
solr_domains_with_a_home_page = convert_list_of_dicts_to_list_of_domains(get_solr_domains_with_a_home_page())

# Top level issues
domains_in_database_but_not_search = set(database_domains) - set(solr_domains_with_a_home_page)
domains_in_search_but_not_database = set(solr_domains_with_a_home_page) - set(database_domains)

# Issues which should be a subset of domains_in_database_but_not_search
domains_in_search_without_a_home_page = set(solr_domains_with_or_without_home) - set(solr_domains_with_a_home_page)

robots_forbidden = []
site_timeout = []
no_documents = []
no_home_in_search = []
unknown = []

for domain in domains_in_database_but_not_search:
    message = get_indexing_log_message(domain)
    if message.startswith('WARNING: No documents found. Likely robots.txt forbidden.'):
        robots_forbidden.append(domain)
    elif message.startswith('WARNING: No documents found. Likely site timeout.'):
        site_timeout.append(domain)
    elif message.startswith('SUCCESS: None documents found.') or message.startswith('WARNING: No documents found. robotstxt/forbidden None, retry/max_reached None'):
        no_documents.append(domain)
    elif domain in domains_in_search_without_a_home_page: # These have a message like "SUCCESS: x documents found." where x > 0 (and none of the documents ave is_home=true)
        no_home_in_search.append(domain)
    else:
        unknown.append(domain)

print("Domains in the database but not the search engine:")
print("Likely robots.txt forbidden: {}".format(robots_forbidden))
print("Likely site timeout: {}".format(site_timeout))
print("No documents found: {}".format(no_documents))
print("No home in search: {}".format(no_home_in_search))
print("Unknown: {}".format(unknown))

# This shouldn't happen any more
#print("\nDomains in the search engine but not the database:")
#print(domains_in_search_but_not_database)
