import json
import psycopg2
import psycopg2.extras
import sys
import os
from urllib.request import urlopen
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(SCRIPT_DIR))
from bulkimport.checkdomains import extract_domain
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

# Database details
# Get database password from ../../.env
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
if not POSTGRES_PASSWORD:
    with open('../../.env') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=')
                if key == 'POSTGRES_PASSWORD': POSTGRES_PASSWORD = value
#database_host = "db" # Dev database
database_host = "142.132.178.149" # Prod database
sql_select_home_pages = 'SELECT home_page, domain FROM tblDomains WHERE moderator_approved = TRUE AND indexing_enabled = TRUE;'

# Solr
#solr_url = 'http://localhost:8983/solr/content/' # Dev
solr_url = 'http://142.132.178.149:8983/solr/content/' # Prod
solr_select_home_pages = "select?fl=url,domain&fq=is_home%3Atrue&q=domain%3A*&sort=domain%20asc&rows=2000"

database_home_page_list = []
database_home_page_dict = {}
database_domain_dict = {}
solr_home_page_list = []
solr_home_page_dict = {}
solr_domain_dict = {}

try:
    conn = psycopg2.connect(host=database_host, dbname="searchmysitedb", user="postgres", password=POSTGRES_PASSWORD)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_select_home_pages)
    results = cursor.fetchall()
    for result in results:
        database_home_page_list.append(result['home_page'])
        database_home_page_dict[result['home_page']] = result['domain']
        database_domain_dict[result['domain']] = result['home_page']
except psycopg2.Error as e:
    print(e.pgerror)

connection = urlopen(solr_url + solr_select_home_pages)
response = json.load(connection)
docs = response['response']['docs']
for doc in docs:
    solr_home_page_list.append(doc['url'])
    solr_home_page_dict[doc['url']] = doc['domain']
    solr_domain_dict[doc['domain']] = doc['url']

home_pages_in_search_but_not_database = set(solr_home_page_list) - set(database_home_page_list)

different_domains = []
different_home_pages = []

for solr_home_page in home_pages_in_search_but_not_database:
    if solr_home_page in solr_home_page_dict:
        domain = solr_home_page_dict[solr_home_page]
    else:
        domain = ""
    if domain in database_domain_dict:
        database_home_page = database_domain_dict[domain]
    else:
        database_home_page = ""
    #print(database_home_page)
    solr_domain = extract_domain(solr_home_page)
    if domain != solr_domain:
        print('domain mismatch: {} -> {}'.format(domain, solr_domain))
        different_domains.append(solr_domain)
    else:
        print('home mismatch: {} -> {}'.format(database_home_page, solr_home_page))
        different_home_pages.append(solr_domain)
    