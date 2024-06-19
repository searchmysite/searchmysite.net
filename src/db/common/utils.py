import json
import os
import psycopg2
import psycopg2.extras
import tldextract
import argparse
from urllib.request import urlopen

# Command line argument parsing
parser = argparse.ArgumentParser(description='Utilities for searchmysite.net.', epilog='Needs access to prod, or for there to be a dev env running.')
parser.add_argument('--env', choices=['dev', 'prod'], default='dev', help='environment to query (default: dev)')
parser.add_argument('--update', default=False, action="store_true", help='make any data updates (default: False)')
args = parser.parse_args()

DATABASE_HOST = '128.140.125.52' if args.env == 'prod' else 'db'
SOLR_URL = 'http://128.140.125.52:8983/solr/content/' if args.env == 'prod' else 'http://localhost:8983/solr/content/'

# Database details
# Get database password from ../../.env
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
if not POSTGRES_PASSWORD:
    with open('../../.env') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=')
                if key == 'POSTGRES_PASSWORD': POSTGRES_PASSWORD = value

# Return appropriate db connection (prod or dev)
def get_db():
    conn = psycopg2.connect(host=DATABASE_HOST, dbname="searchmysitedb", user="postgres", password=POSTGRES_PASSWORD)
    return conn

def get_args():
    return args

# Solr queries
solr_domains_with_home_page = "select?fl=domain,url&fq=is_home%3Atrue&q=domain%3A*&sort=domain%20asc&rows=10000"
solr_domains_with_or_without_home = "select?facet.field=domain&facet.limit=10000&facet.sort=index&facet.mincount=1&facet=true&fq=relationship%3Aparent&indent=true&q.op=OR&q=*%3A*&rows=0&useParams="

# SQL

sql_select_all_domains = 'SELECT * FROM tblDomains;' # This returns all domains, even pending ones or moderator rejected or indexing disabled

sql_select_indexing_log_message = "SELECT domain, message FROM tblindexinglog WHERE domain IN ((%s)) AND status = 'COMPLETE' ORDER BY timestamp DESC LIMIT 1;"

# This is a version of ../../web/content/dynamic/searchmysite/sql.py modified to include other fields - if that is updated this should be too
sql_select_indexed_domains = "SELECT d.domain, d.home_page, l.tier FROM tblDomains d INNER JOIN tblListingStatus l ON d.domain = l.domain WHERE d.indexing_enabled = TRUE AND l.status = 'ACTIVE' ORDER BY domain;"

# These are copied from ../../web/content/dynamic/searchmysite/sql.py - if they are updated these should be too
sql_select_domains_allowing_subdomains = "SELECT setting_value FROM tblSettings WHERE setting_name = 'domain_allowing_subdomains';"
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
    "content_chunks_limit = tblTiers.default_content_chunks_limit, "\
    "on_demand_reindexing = tblTiers.default_on_demand_reindexing, "\
    "api_enabled = tblTiers.default_api_enabled, "\
    "indexing_enabled = TRUE, "\
    "indexing_status = 'PENDING', "\
    "indexing_status_changed = NOW() "\
    "FROM tblTiers WHERE tblTiers.tier = 1 and tblDomains.domain = (%s);"

# Functions called externally

def convert_list_of_dicts_to_list_of_domains(list_of_dicts):
    list_of_domains = []
    for dict in list_of_dicts:
        list_of_domains.append(dict['domain'])
    return list_of_domains

def get_solr_domains_with_a_home_page():
    solr_domains = []
    connection = urlopen(SOLR_URL + solr_domains_with_home_page)
    response = json.load(connection)
    results = response['response']['docs']
    for result in results:
        solr_domain = {}
        solr_domain['domain'] = result['domain']
        solr_domain['url'] = result['url']
        solr_domains.append(solr_domain)
    return solr_domains

def get_solr_domains_with_or_without_home():
    solr_domains = []
    connection = urlopen(SOLR_URL + solr_domains_with_or_without_home)
    response = json.load(connection)
    results = response['facet_counts']['facet_fields']['domain']
    for result in results:
        if isinstance(result, str):
            solr_domains.append(result) # result is a list of domains and counts like ["0d.be",50,"0xfab1.net",50,...] so just take the domains
    return solr_domains

def get_indexing_log_message(domain):
    message = ""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_select_indexing_log_message, (domain, ))
    result = cursor.fetchone()
    if result and 'domain' in result and result['domain']:
        message = result['message']
    return message

def select_all_domains():
    all_domains = []
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_select_indexed_domains)
    results = cursor.fetchall()
    for result in results:
        all_domains.append(result['domain'])
    return all_domains

def insert_domain(domain, home_page, category, tier):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_insert_domain, (domain, home_page, category))
    cursor.execute(sql_insert_basic_listing, (domain, tier))
    conn.commit()

def approve_domain(domain, moderator):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_update_basic_approved, (domain, moderator, domain))
    conn.commit()

# This is based on ../../web/content/dynamic/searchmysite/adminutils.py - if that is updated this should be too
# It returns a list of dicts though, rather than a list of domains
def select_indexed_domains():
    indexed_domains = []
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_select_indexed_domains)
    results = cursor.fetchall()
    for result in results:
        indexed_domain = {}
        indexed_domain['domain'] = result['domain']
        indexed_domain['home_page'] = result['home_page']
        indexed_domain['tier'] = result['tier']
        indexed_domains.append(indexed_domain)
    return indexed_domains

# This is copied from ../../web/content/dynamic/searchmysite/adminutils.py - if that is updated this should be too
# The cursor.execute(searchmysite.sql.sql_select_domains_allowing_subdomains) line should be updated to remove searchmysite.sql.
def extract_domain(url):
    # Get the domain from the URL
    if not url: url = ""
    # returns subdomain, domain, suffix, is_private=True|False), also registered_domain (domain+'.'+suffix) and fqdn (subdomain+'.'+domain+'.'+suffix)
    tld = tldextract.extract(url) 
    domain = tld.registered_domain
    if tld.domain == 'localhost' and tld.suffix == '': # special case for localhost which has tld.registered_domain = ''
        domain = tld.domain
    domain = domain.lower() # lowercase the domain to help prevent duplicates
    # Look up list of domains which allow subdomains from database
    domains_allowing_subdomains = []
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_select_domains_allowing_subdomains)
    results = cursor.fetchall()
    for result in results:
        domains_allowing_subdomains.append(result['setting_value'])
    # Add subdomain if in domains_allowing_subdomains
    if domain in domains_allowing_subdomains: # special domains where a site can be on a subdomain
        if tld.subdomain and tld.subdomain != "":
            domain = tld.subdomain + "." + domain
    return domain
