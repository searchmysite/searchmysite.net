import json
import psycopg2
import psycopg2.extras
import sys
import os

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
#database_host = "searchmysite.net" # Prod database

sql_pending = "INSERT INTO tblPendingDomains "\
    "(domain, home_page, date_domain_added, owner_submitted, submission_method) "\
    "VALUES ((%s), (%s), now(), FALSE, 'SQL');"

sql_indexed = "INSERT INTO tblIndexedDomains "\
    "(domain, home_page, date_domain_added, owner_verified, validation_method, "\
    "expire_date, api_enabled, indexing_frequency, indexing_page_limit, indexing_current_status, indexing_status_last_updated) "\
    "VALUES ((%s), (%s), now(), FALSE, 'SQL', "\
    "now() + '1 year', FALSE, '7 days', 50, 'PENDING', now());"

# If valid and reviewed are True and already_in_list and already_in_database are False
# this will insert straight into tblIndexedDomains for indexing
# If valid is True and already_in_list and already_in_database are False, but reviewed is False
# this will insert into tblPendingDomains, requiring manual inspection prior to approve and move to tblIndexedDomains 
# (or rejection and move to tblExcludeDomains)

def insert_pending(domain, home_page):
    conn = psycopg2.connect(host=database_host, dbname="searchmysitedb", user="postgres", password=POSTGRES_PASSWORD)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_pending, (domain, home_page, ))
    conn.commit()
    print("insert pending", domain, home_page)

def insert_indexed(domain, home_page):
    conn = psycopg2.connect(host="searchmysite.net", dbname="searchmysitedb", user="postgres", password=POSTGRES_PASSWORD)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_indexed, (domain, home_page, ))
    conn.commit()
    print("insert indexed", domain, home_page)

with open(input_file) as json_file:
    domains = json.load(json_file)
    for domain in domains:
        if domain['valid'] == True: # If not valid the already_in_list and already_in_database check won't have been performed
            if domain['already_in_list'] == False and domain['already_in_database'] == False:
                if domain['reviewed'] == True:
                    insert_indexed(domain['domain'], domain['home_page'])
                elif domain['reviewed'] == False:
                    insert_pending(domain['domain'], domain['home_page'])
                else:
                    print("Issue with {}".format(domain['domain']))
            else:
                print("Skipping {}: already present".format(domain['domain']))
        else:
            print("Skipping {}: not valid".format(domain['domain']))
