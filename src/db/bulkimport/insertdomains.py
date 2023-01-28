import json
import psycopg2
import psycopg2.extras
import sys
import os


# Instructions:
# See comments at the start of checkdomains.py

if len(sys.argv) > 1:
    inp = sys.argv[1]
else:
    exit("You need to provide an input, e.g. sitelist1 will load from data/sitelist1.json")

# Get database password from ../../.env
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
if not POSTGRES_PASSWORD:
    with open('../../.env') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=')
                if key == 'POSTGRES_PASSWORD': POSTGRES_PASSWORD = value

input_file = 'data/' + inp + '.json'

database_host = "db" # Dev database
#database_host = "142.132.178.149" # Prod database

# This is copied from ../../web/content/dynamic/searchmysite/sql.py - if that is updated this should be too
sql_insert_domain = "INSERT INTO tblDomains "\
    "(domain, home_page, domain_first_submitted, category, include_in_public_search, indexing_type) "\
    "VALUES ((%s), (%s), NOW(), (%s), TRUE, 'spider/default');"

sql_insert_basic_listing = "INSERT INTO tblListingStatus (domain, tier, status, status_changed, pending_state, pending_state_changed) "\
    "VALUES ((%s), (%s), 'PENDING', NOW(), 'MODERATOR_REVIEW', NOW());"

sql_update_basic_approved = "UPDATE tblListingStatus "\
    "SET status = 'ACTIVE', status_changed = NOW(), pending_state = NULL, pending_state_changed = NOW(), listing_start = NOW(), listing_end = NOW() + (SELECT listing_duration FROM tblTiers WHERE tier = 1) "\
    "WHERE domain = (%s) AND status = 'PENDING' AND tier = 1 AND pending_state = 'MODERATOR_REVIEW'; "\
    "UPDATE tblDomains SET "\
    "moderator_approved = TRUE, "\
    "moderator = (%s), "\
    "full_reindex_frequency = tblTiers.default_full_reindex_frequency, "\
    "incremental_reindex_frequency = tblTiers.default_incremental_reindex_frequency, "\
    "indexing_page_limit = tblTiers.default_indexing_page_limit, "\
    "on_demand_reindexing = tblTiers.default_on_demand_reindexing, "\
    "api_enabled = tblTiers.default_api_enabled, "\
    "indexing_enabled = TRUE, "\
    "indexing_status = 'PENDING', "\
    "indexing_status_changed = NOW() "\
    "FROM tblTiers WHERE tblTiers.tier = 1 and tblDomains.domain = (%s);"


# If valid and reviewed are True and already_in_list and already_in_database are False
# this will insert straight into tblDomains with moderator_approved TRUE for indexing
# If valid is True and already_in_list and already_in_database are False, but reviewed is False
# this will insert into tblDomains with moderator_approved NULL, requiring manual inspection prior to 
# approval (or rejection)

def insert_domain(domain, home_page, category, tier):
    conn = psycopg2.connect(host=database_host, dbname="searchmysitedb", user="postgres", password=POSTGRES_PASSWORD)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_insert_domain, (domain, home_page, category))
    cursor.execute(sql_insert_basic_listing, (domain, tier))
    conn.commit()
    print("inserting domain: {}, home page: {}, category: {}, tier: {}".format(domain, home_page, category, tier))

def approve_domain(domain, moderator):
    conn = psycopg2.connect(host=database_host, dbname="searchmysitedb", user="postgres", password=POSTGRES_PASSWORD)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_update_basic_approved, (domain, moderator, domain))
    conn.commit()
    print("approving domain: {}, moderator: {}".format(domain, moderator))

with open(input_file) as json_file:
    domains = json.load(json_file)
    for domain in domains:
        if domain['valid'] == True: # If not valid the already_in_list and already_in_database check won't have been performed
            if domain['already_in_list'] == False and domain['already_in_database'] == False:
                insert_domain(domain['domain'], domain['home_page'], 'personal-website', 1) # category and tier hardcoded
                if domain['reviewed'] == True:
                    approve_domain(domain['domain'], 'michael-lewis.com') # moderator hardcoded
                else:
                    print("Issue with {}".format(domain['domain']))
            else:
                print("Skipping {}: already present".format(domain['domain']))
        else:
            print("Skipping {}: not valid".format(domain['domain']))
