import json
import sys
import psycopg2
import psycopg2.extras
import os
from urllib.request import urlopen
# This utility connects to the database and search index, and checks whether:
# 1. There are any domains in the database which aren't in the search index
# 2. There are any domains in the search index which aren't ion the database 

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
database_host = "searchmysite.net" # Prod database
sql_select_domains = 'SELECT domain FROM tblIndexedDomains ORDER BY domain ASC LIMIT 2000;'

# Solr
#solr_url = 'http://localhost:8983/solr/content/' # Dev
solr_url = 'http://searchmysite.net:8983/solr/content/' # Prod
solr_select_domains = "select?fl=domain&fq=is_home%3Atrue&q=domain%3A*&sort=domain%20asc&rows=2000"

database_domains = []
solr_domains = []

try:
    conn = psycopg2.connect(host=database_host, dbname="searchmysitedb", user="postgres", password=POSTGRES_PASSWORD)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_select_domains)
    dd = cursor.fetchall()
    for [d] in dd:
        database_domains.append(d)
except psycopg2.Error as e:
    print(e.pgerror)

connection = urlopen(solr_url + solr_select_domains)
response = json.load(connection)
sd = response['response']['docs']
for d in sd:
    solr_domains.append(d['domain'])

#print("Domains in the database: {}".format(database_domains))
#print("Domains in the search engine: {}".format(solr_domains))
print("Domains in the database but not the search engine: {}".format(set(database_domains) - set(solr_domains)))
print("Domains in the search engine but not the database: {}".format(set(solr_domains) - set(database_domains)))
