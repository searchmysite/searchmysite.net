import json
from urllib.request import urlopen, Request
import psycopg2
import psycopg2.extras
import tldextract
import logging
import re
import httplib2
from dateutil.parser import parse, ParserError
from bs4 import BeautifulSoup, SoupStrainer
from common import config

db_password = config.DB_PASSWORD
db_name = config.DB_NAME
db_user = config.DB_USER
db_host = config.DB_HOST

domains_sql = "SELECT DISTINCT domain FROM tblListingStatus WHERE status = 'ACTIVE';"

domains_allowing_subdomains_sql = "SELECT setting_value FROM tblSettings WHERE setting_name = 'domain_allowing_subdomains';"

update_indexing_status_sql = "UPDATE tblDomains "\
    "SET full_indexing_status = (%s), full_indexing_status_changed = now() "\
    "WHERE domain = (%s); "\
    "INSERT INTO tblIndexingLog (domain, status, timestamp, message) "\
    "VALUES ((%s), (%s), now(), (%s));"

indexing_log_sql = "SELECT * FROM tblIndexingLog WHERE domain = (%s) AND status = 'COMPLETE' ORDER BY timestamp DESC LIMIT 1;"

get_last_complete_indexing_log_message_sql = "SELECT message FROM tblIndexingLog WHERE domain = (%s) AND status = 'COMPLETE' ORDER BY timestamp DESC LIMIT 1;"

deactivate_indexing_sql = "UPDATE tblDomains SET "\
    "indexing_enabled = FALSE, indexing_disabled_changed = now(), indexing_disabled_reason = (%s) WHERE domain = (%s);"

get_expired_unverified_sites_sql = "SELECT d.domain, l.tier from tblDomains d "\
    "INNER JOIN tblListingStatus l ON d.domain = l.domain "\
    "WHERE l.listing_end < now() "\
    "AND l.status = 'ACTIVE' "\
    "AND l.tier = 1 "\
    "AND indexing_type = 'spider/default' "\
    "ORDER BY domain_first_submitted ASC;"

expire_unverified_site_sql = "UPDATE tblDomains SET moderator_approved = NULL where domain = (%s);"\
    "UPDATE tblListingStatus SET status = 'PENDING', status_changed = NOW(), pending_state = 'MODERATOR_REVIEW', pending_state_changed = NOW() "\
    "WHERE domain = (%s) AND tier = (%s);"

check_for_stuck_jobs_sql = "SELECT * FROM tblDomains "\
    "WHERE indexing_type = 'spider/default' "\
    "AND full_indexing_status = 'RUNNING' "\
    "AND full_indexing_status_changed + '6 hours' < NOW();"

solr_url = config.SOLR_URL
solr_query_to_get_indexed_outlinks = "select?q=*%3A*&fq=indexed_outlinks%3A*{}*&fl=url,indexed_outlinks&rows=10000"
solr_delete_query = "update?commit=true"
solr_delete_headers = {'Content-Type': 'text/xml'}
solr_delete_data = "<delete><query>domain:{}</query></delete>"


# Database utils
# --------------

# Get all domains
def get_all_domains():
    domains = []
    try:
        conn = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_password)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(domains_sql)
        dd = cursor.fetchall()
        for [d] in dd:
            domains.append(d)
    except psycopg2.Error as e:
        logger = logging.getLogger()
        logger.error('get_all_domains: {}'.format(e.pgerror))
    finally:
        conn.close()
    return domains

# Get the domains which allow subdomains, e.g. github.io 
def get_domains_allowing_subdomains():
    domains_allowing_subdomains = []
    try:
        conn = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_password)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(domains_allowing_subdomains_sql)
        domains_allowing_subdomains_results = cursor.fetchall()
        for domains_allowing_subdomain in domains_allowing_subdomains_results:
            domains_allowing_subdomains.append(domains_allowing_subdomain['setting_value'])
    except psycopg2.Error as e:
        logger = logging.getLogger()
        logger.error('get_domains_allowing_subdomains: {}'.format(e.pgerror))
    finally:
        conn.close()
    return domains_allowing_subdomains

# Update indexing log
# status either RUNNING or COMPLETE
def update_indexing_log(domain, status, message):
    try:
        conn = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_password)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(update_indexing_status_sql, (status, domain, domain, status, message,))
        conn.commit()
    except psycopg2.Error as e:
        logger = logging.getLogger()
        logger.error('update_indexing_log: {}'.format(e.pgerror))
    finally:
        conn.close()
    return

# Get the latest indexing log message where status is COMPLETE (message will start SUCCESS or WARNING)
def get_last_complete_indexing_log_message(domain):
    log_message = ""
    try:
        conn = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_password)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(get_last_complete_indexing_log_message_sql, (domain, ))
        log_messages = cursor.fetchone()
        if log_messages and log_messages['message']:
            log_message = log_messages['message']
    except psycopg2.Error as e:
        logger = logging.getLogger()
        logger.error('get_last_complete_indexing_log_message: {}'.format(e.pgerror))
    finally:
        conn.close()
    return log_message

# Deactivate indexing
def deactivate_indexing(domain, reason):
    try:
        conn = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_password)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(deactivate_indexing_sql, (reason, domain,))
        conn.commit()
    except psycopg2.Error as e:
        logger = logging.getLogger()
        logger.error('deactivate_indexing: {}'.format(e.pgerror))
    finally:
        conn.close()
    return

# Check for stuck jobs
def check_for_stuck_jobs():
    logger = logging.getLogger()
    try:
        conn = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_password)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(check_for_stuck_jobs_sql)
        results = cursor.fetchall()
        stuck_domains = []
        for result in results:
            stuck_domains.append(result['domain'])
        if stuck_domains:
            logger.warning('The following domains have had indexing RUNNING for over 6 hours, so something is likely to be wrong: {}'.format(stuck_domains))
    except psycopg2.Error as e:
        logger.error(' %s' % e.pgerror)
    finally:
        conn.close()

# Expire unverified ('QuickAdd', 'SQL') sites
def expire_unverified_sites():
    expired_unverified_sites = []
    logger = logging.getLogger()
    try:
        conn = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_password)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(get_expired_unverified_sites_sql)
        results = cursor.fetchall()
        for result in results:
            expired_unverified_sites.append(result['domain'])
        if expired_unverified_sites:
            for expired_unverified_site in expired_unverified_sites:
                logger.info('Expiring the following unverified domain: {}'.format(expired_unverified_site))
                cursor.execute(expire_unverified_site_sql, (expired_unverified_site,))
                conn.commit()
                solr_delete_domain(expired_unverified_site)
    except psycopg2.Error as e:
        logger.error('expire_unverified_sites: {}'.format(e.pgerror))
    finally:
        conn.close()
    return expired_unverified_sites



# Solr utils
# ----------

# Logic for generating all the indexed_inlinks for a domain:
# Step 1:
# Search for any indexed_outlinks to that domain, i.e.
# /solr/content/select?q=*%3A*&fq=indexed_outlinks%3A*{domain}*&fl=url,indexed_outlinks&rows=10000
# This will return urls each with a list of indexed_outlinks to that domain (and potentially other domains).
# Note that it doesn't appear possible to restrict indexed_outlinks to just the domain specified in fq=indexed_outlinks%3A*{domain}*
# (see https://issues.apache.org/jira/browse/SOLR-3955) so other domains will need to be filtered out later.
# Step 2:
# Invert, so instead of a dict of indexed links each with a list of indexed_outlinks 
# it is a dict of indexed_outlinks each with a list of indexed links.
# The indexed_outlinks, if matching the domain, will be the ones that will have indexed_inlinks value set for them, and the value of the
# indexed_inlinks will be the list of urls.
def get_all_indexed_inlinks_for_domain(domain):
    indexed_inlinks = {}
    solrquery = solr_query_to_get_indexed_outlinks.format(domain)
    connection = urlopen(solr_url + solrquery)
    results = json.load(connection)
    if results['response']['docs']:
        for doc in results['response']['docs']:
            url = doc['url']
            indexed_outlinks = doc['indexed_outlinks']
            for indexed_outlink in indexed_outlinks:
                if domain in indexed_outlink:
                    if indexed_outlink not in indexed_inlinks:
                        indexed_inlinks[indexed_outlink] = [url]
                    else:
                        indexed_inlinks[indexed_outlink].append(url)
    return indexed_inlinks

# Remove all pages from a domain from the Solr index
def solr_delete_domain(domain):
    solrurl = config.SOLR_URL
    solrquery = solrurl + solr_delete_query
    data = solr_delete_data.format(domain)
    req = Request(solrquery, data.encode("utf8"), solr_delete_headers)
    response = urlopen(req)
    results = response.read()


# Domain utils
# ------------

# Extract domain from a URL, where domain could be a subdomain if that domain allows subdomains
# This is a variant of ../../web/content/dynamic/admin/util.py which takes domains_allowing_subdomains as an input parameter
# because don't want a database lookup every time this is called in this context
def extract_domain_from_url(url, domains_allowing_subdomains):
    tld = tldextract.extract(url) # returns [subdomain, domain, suffix]
    domain = '.'.join(tld[1:]) if tld[2] != '' else tld[1] # if suffix empty, e.g. localhost, just use domain
    domain = domain.lower() # lowercase the domain to help prevent duplicates
    # Add subdomain if in domains_allowing_subdomains
    if domain in domains_allowing_subdomains: # special domains where a site can be on a subdomain
        if tld[0] and tld[0] != "":
            domain = tld[0] + "." + domain
    return domain


# String utils
# ------------

# Solr's DatePointField (pdate) requires UTC time in the DateTimeFormatter.ISO_INSTANT format, i.e.
# YYYY-MM-DDThh:mm:ssZ
# This converts strings to that format.
# Some sites have date strings which throw a ParserError, 
# e.g. <meta property="article:published_time" content="2019-02-21_1220"> throws a 
# dateutil.parser._parser.ParserError: Unknown string format: 2019-02-21_1220
# So catch those
def convert_string_to_utc_date(date_string):
    date_utc = None
    if date_string != '' and date_string != None:
        try:
            date_string = parse(date_string) # convert string of unknown format to datetime object
            date_utc = date_string.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ParserError:
            logger = logging.getLogger()
            logger.info('Unable to parse date string {}'.format(date_string))
    return date_utc

# Convert Python datetime objects to Solr's format
def convert_datetime_to_utc_date(date_datetime):
    date_utc = None
    if date_datetime != '' and date_datetime != None:
        date_utc = date_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    return date_utc

# Convert BeautifulSoup html object to relatively clean plain text
def get_text(html):
    text = html.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = ' \n '.join(chunk for chunk in chunks if chunk)
    if text == "": text = None
    return text


# Wikipedia utils
# ---------------

# Get latest completed import date
# Assumes the log status is "COMPLETE" and message of the format "Using export: 20210927"
def get_latest_completed_wikipedia_import(domain):
    completed_import_date = ""
    try:
        conn = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_password)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(indexing_log_sql, (domain, ))
        result = cursor.fetchone()
        if result and result['message']:
            r = re.search('Using export: (.*)', result['message'])
            if r:
                completed_import_date = r.group(1)
        conn.commit()
    except psycopg2.Error as e:
        logger = logging.getLogger()
        logger.error('update_indexing_log: {}'.format(e.pgerror))
    finally:
        conn.close()
    return completed_import_date

# Get latest available wikipedia export
def get_latest_available_wikipedia_export(dump_location):
    latest_available_wikipedia_export = ""
    exports = []
    http = httplib2.Http()
    status, response = http.request(dump_location)
    for link in BeautifulSoup(response, parse_only=SoupStrainer('a'), features="lxml"):
        if link.has_attr('href'):
            if link['href'][:8].isdigit():
                exports.append(link['href'][:8])
    sorted_exports = sorted(exports)
    return sorted_exports[-1]
