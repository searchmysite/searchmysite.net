#!/usr/bin/env python3
import json
import psycopg2
import psycopg2.extras
import sys
import os
from urllib.request import urlopen
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(SCRIPT_DIR))
from common.utils import get_args, extract_domain, select_indexed_domains, get_solr_domains_with_a_home_page

# This utility connects to the database and search index, and checks whether
# the home page in the database has been redirected to a different home page.
# Within those, there are two sub-categories:
# 1. Where the new (Solr) domain is different from the start (database) domain
#    e.g. home in database is http://kevq.uk so domain is kevq.uk, but home in 
#    Solr is https://kevquirk.com/ so domain should be kevquirk.com. These are
#    problematic because only the home page will be indexed not the rest of the 
#    site, so these should be corrected.
# 2. Where the domains are the same but the home page is different, e.g. home in
#    database starts http but on Solr starts https, or ends / but in Solr ends /wp/.
#    These aren't usually problematic because the site should still be indexed,
#    although might still indecate a problem if the home is redirected to something
#    like /RUNCLOUD-7G-WAF-BLOCKED .
# Currently just reporting the first category.
# Also just printing the SQL to fix the first category for now, so it can be run domain by domain, 
# until there's confidence to make bulk changes
# Final note: Still want to manually verify the changes, because some of the redirects are to 
# shared domains, which won't work, e.g. abc.com -> github.com/abc or abc.me -> persumi.com/u/abc

sql_insert_new_domain = "INSERT INTO tblDomains "\
    "(domain, home_page, category, domain_first_submitted, email, include_in_public_search, moderator_approved, moderator_action_changed, moderator, full_reindex_frequency, indexing_page_limit, on_demand_reindexing, api_enabled, indexing_enabled, indexing_type, indexing_status, indexing_status_changed) "\
    "(SELECT \'{new_domain}\', \'{new_home_page}\', category, domain_first_submitted, email, include_in_public_search, moderator_approved, moderator_action_changed, moderator, full_reindex_frequency, indexing_page_limit, on_demand_reindexing, api_enabled, indexing_enabled, indexing_type, 'PENDING', indexing_status_changed "\
    "FROM tblDomains WHERE domain = \'{old_domain}\');"

sql_insert_listing_status = "INSERT INTO tblListingStatus "\
    "(domain, tier, status, status_changed, pending_state, pending_state_changed, listing_start, listing_end) "\
    "(SELECT \'{new_domain}\', tier, status, status_changed, pending_state, pending_state_changed, listing_start, listing_end "\
    "FROM tblListingStatus WHERE domain = \'{old_domain}\');"

args = get_args()

def get_mismatched_home_pages(database_details, search_details):
    mismatched_home_pages = []
    for search_detail in search_details:
        search_home = search_detail['url']
        search_domain = search_detail['domain']
        for database_detail in database_details:
            if database_detail['domain'] == search_domain:
                if database_detail['home_page'] != search_home:
                    search_domain = extract_domain(search_home) # This can be a bit slow so best only do it where necessary, e.g. where home pages don't match
                    mismatched_home_page = {}
                    mismatched_home_page['search_home'] = search_home
                    mismatched_home_page['search_domain'] = search_domain
                    mismatched_home_page['database_home'] = database_detail['home_page']
                    mismatched_home_page['database_domain'] = database_detail['domain']
                    mismatched_home_page['tier'] = database_detail['tier']
                    mismatched_home_pages.append(mismatched_home_page)
    return mismatched_home_pages

# Mismatched domains will be a subset of mistmatched_home_pages
def get_mismatched_domains(mismatched_home_pages, database_details):
    mismatched_domains = []
    for mismatched_home_page in mismatched_home_pages:
        search_domain = mismatched_home_page['search_domain']
        database_domain = mismatched_home_page['database_domain']
        if search_domain != database_domain:
            if any(database_detail['domain'] == search_domain for database_detail in database_details): # Only add new domains that don't already exist, to prevent an error
                print('\n{} -> {} but there is already a separate entry for {}'.format(database_domain, search_domain, search_domain))
            elif mismatched_home_page['tier'] != 1: # Only add new tier 1 domains for now, because tier 2 and 3 may require additional SQL
                print('\n{} -> {} but this is not a tier 1 site, so additional SQL may be required'.format(database_domain, search_domain))
            elif search_domain in ['github.com']:
                print('\n{} -> {} but this is a shared domain'.format(database_domain, search_domain))
            else:
                mismatched_domains.append(mismatched_home_page)
    return mismatched_domains

database_details = select_indexed_domains()
search_details = get_solr_domains_with_a_home_page()

mismatched_home_pages = get_mismatched_home_pages(database_details, search_details)
#for mismatch in mismatched_home_pages:
#    print("database_home: {}, search_home: {} (database domain: {}, search_domain: {}), ".format(mismatch['database_home'], mismatch['search_home'], mismatch['database_domain'], mismatch['search_domain']))

mismatched_domains = get_mismatched_domains(mismatched_home_pages, database_details)
for mismatch in mismatched_domains:
    old_domain = mismatch['database_domain']
    new_domain = mismatch['search_domain']
    old_home_page = mismatch['database_home']
    new_home_page = mismatch['search_home']
    tier = mismatch['tier']
    print("\n{} -> {} ({} -> {}) tier {}".format(old_domain, new_domain, old_home_page, new_home_page, tier))
    if args.update:
        print(sql_insert_new_domain.format(new_domain=new_domain, new_home_page=new_home_page, old_domain=old_domain))
        print(sql_insert_listing_status.format(new_domain=new_domain, old_domain=old_domain))

