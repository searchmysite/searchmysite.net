import json
from urllib.request import urlopen, Request
import psycopg2
import psycopg2.extras
import tldextract
import logging
from os import environ
import re
import httplib2
import smtplib, ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dateutil.parser import parse, ParserError
from bs4 import BeautifulSoup, SoupStrainer
from sentence_transformers import SentenceTransformer
from langchain.text_splitter import RecursiveCharacterTextSplitter
from common import config


# Database config
db_password = config.DB_PASSWORD
db_name = config.DB_NAME
db_user = config.DB_USER
db_host = config.DB_HOST

# Email config
smtp_server = environ.get('SMTP_SERVER')
smtp_port = environ.get('SMTP_PORT')
smtp_from_email = environ.get('SMTP_FROM_EMAIL')
smtp_from_password = environ.get('SMTP_FROM_PASSWORD')
smtp_to_email = environ.get('SMTP_TO_EMAIL')

# SQL
sql_select_domains = "SELECT d.domain from tblDomains d INNER JOIN tblListingStatus l ON d.domain = l.domain WHERE l.status = 'ACTIVE' AND d.indexing_enabled = TRUE;"
sql_select_domains_allowing_subdomains = "SELECT setting_value FROM tblSettings WHERE setting_name = 'domain_allowing_subdomains';"
sql_update_indexing_status = "UPDATE tblDomains "\
    "SET indexing_status = (%s), indexing_status_changed = now() "\
    "WHERE domain = (%s); "\
    "INSERT INTO tblIndexingLog (domain, status, timestamp, message) "\
    "VALUES ((%s), (%s), now(), (%s));"
sql_update_indexing_complete = "UPDATE tblDomains SET last_index_completed = now() WHERE domain = (%s);"
sql_update_full_indexing_complete = "UPDATE tblDomains SET last_index_completed = now(), last_full_index_completed = now() WHERE domain = (%s);"
sql_select_indexing_log = "SELECT * FROM tblIndexingLog WHERE domain = (%s) AND status = 'COMPLETE' ORDER BY timestamp DESC LIMIT 1;"
sql_select_last_complete_indexing_log_message = "SELECT message FROM tblIndexingLog WHERE domain = (%s) AND status = 'COMPLETE' ORDER BY timestamp DESC LIMIT 1;"
sql_deactivate_indexing = "UPDATE tblDomains SET "\
    "indexing_enabled = FALSE, indexing_disabled_changed = now(), indexing_disabled_reason = (%s) WHERE domain = (%s);"
sql_select_expired_listings = "SELECT d.domain, d.email from tblDomains d "\
    "INNER JOIN tblListingStatus l ON d.domain = l.domain "\
    "WHERE l.listing_end < now() "\
    "AND l.status = 'ACTIVE' "\
    "AND l.tier = (%s) "\
    "AND d.indexing_type = 'spider/default' "\
    "ORDER BY d.domain_first_submitted ASC;"
sql_expire_tier1_listing = "UPDATE tblDomains SET moderator_approved = NULL where domain = (%s);"\
    "UPDATE tblListingStatus SET status = 'PENDING', status_changed = NOW(), pending_state = 'MODERATOR_REVIEW', pending_state_changed = NOW() "\
    "WHERE domain = (%s) AND tier = 1;"
sql_expire_tier2or3_listing = "UPDATE tblListingStatus SET status = 'EXPIRED', status_changed = NOW() WHERE domain = (%s) AND tier = (%s); "\
    "INSERT INTO tblListingStatus (domain, tier, status, status_changed, listing_start, listing_end) "\
    "VALUES ((%s), (%s), 'ACTIVE', NOW(), NOW(), NOW() + (SELECT listing_duration FROM tblTiers WHERE tier = (%s))) "\
    "  ON CONFLICT (domain, tier) "\
    "  DO UPDATE SET "\
    "    status = EXCLUDED.status, "\
    "    status_changed = EXCLUDED.status_changed, "\
    "    listing_start = EXCLUDED.listing_start, "\
    "    listing_end = EXCLUDED.listing_end;"
sql_reset_indexing_defaults = "UPDATE tblDomains SET "\
    "full_reindex_frequency = tblTiers.default_full_reindex_frequency, "\
    "incremental_reindex_frequency = tblTiers.default_incremental_reindex_frequency, "\
    "indexing_page_limit = tblTiers.default_indexing_page_limit, "\
    "on_demand_reindexing = tblTiers.default_on_demand_reindexing, "\
    "api_enabled = tblTiers.default_api_enabled, "\
    "indexing_enabled = TRUE, "\
    "indexing_status = 'PENDING', "\
    "indexing_status_changed = NOW() "\
    "FROM tblTiers WHERE tblTiers.tier = (%s) and tblDomains.domain = (%s);"
sql_select_stuck_jobs = "SELECT * FROM tblDomains "\
    "WHERE indexing_type = 'spider/default' "\
    "AND indexing_status = 'RUNNING' "\
    "AND indexing_status_changed + '6 hours' < NOW();"
sql_select_user_entered = "SELECT web_feed_user_entered, sitemap_user_entered FROM tblDomains WHERE domain = (%s);"
sql_update_auto_discovered = "UPDATE tblDomains SET web_feed_auto_discovered = (%s), sitemap_auto_discovered = (%s) WHERE domain = (%s);"

# Solr config and queries
solr_url = config.SOLR_URL
solr_query_to_get_indexed_outlinks = "select?q=*%3A*&fq=indexed_outlinks%3A*{}*&fl=url,indexed_outlinks&rows=10000"
solr_query_to_get_already_indexed_links = "select?q=domain%3A{}&fq=!relationship%3Achild&fl=url&rows=1000"
# The solr_query_to_get_content includes fl=content_chunks,[child] to get the correctly nested child documents, and fq=!relationship:child 
# to ensure the child documents don't also appear as siblings (noting that fq=relationship:parent can't be used until all pages have that value set)  
solr_query_to_get_content = "select?q=*%3A*&fq=domain%3A{}&fq=!relationship:child&fl=id,url,domain,content,content_last_modified,content_chunk_no,content_chunk_text,content_chunk_vector,relationship,content_chunks,[child]&rows=1000"
solr_delete_query = "update?commit=true"
solr_delete_headers = {'Content-Type': 'text/xml'}
solr_delete_data = "<delete><query>domain:{}</query></delete>"

# Content chunking (for embedding) config
chunk_size = 500 # in chars. note that sentence-transformers/all-MiniLM-L6-v2 has max input text 256 word pieces so this works if av word piece is 2 chars
chunk_overlap = 50
embedding_model = 'sentence-transformers/all-MiniLM-L6-v2'


# Database utils
# --------------

# Get all domains
def get_all_domains():
    domains = []
    try:
        conn = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_password)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_select_domains)
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
        cursor.execute(sql_select_domains_allowing_subdomains)
        domains_allowing_subdomains_results = cursor.fetchall()
        for domains_allowing_subdomain in domains_allowing_subdomains_results:
            domains_allowing_subdomains.append(domains_allowing_subdomain['setting_value'])
    except psycopg2.Error as e:
        logger = logging.getLogger()
        logger.error('get_domains_allowing_subdomains: {}'.format(e.pgerror))
    finally:
        conn.close()
    return domains_allowing_subdomains

# Update indexing status
# This is called at both the start and the end of indexing 
# status either RUNNING or COMPLETE
# full_index only required if status = 'COMPLETE'
def update_indexing_status(domain, full_index, status, message):
    try:
        conn = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_password)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_update_indexing_status, (status, domain, domain, status, message,))
        conn.commit()
        if status == 'COMPLETE':
            if full_index == True:
                cursor.execute(sql_update_full_indexing_complete, (domain,))
            else:
                cursor.execute(sql_update_indexing_complete, (domain,))
            conn.commit()
    except psycopg2.Error as e:
        logger = logging.getLogger()
        logger.error('update_indexing_status: {}'.format(e.pgerror))
    finally:
        conn.close()
    return

# Get the latest indexing log message where status is COMPLETE (message will start SUCCESS or WARNING)
def get_last_complete_indexing_log_message(domain):
    log_message = ""
    try:
        conn = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_password)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_select_last_complete_indexing_log_message, (domain, ))
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
        cursor.execute(sql_deactivate_indexing, (reason, domain,))
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
        cursor.execute(sql_select_stuck_jobs)
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

# Expire listings
# The expiry process varies per tier.
# Tier 1 expiry:
# (i) the site remains on the same tier (tier 1) but has status set to PENDING and pending_state set to 'MODERATOR_REVIEW', and
# (ii) the site is removed from the search engine results 
# Tier 2 expiry:
# (i) the site drops a tier (BTW moderator will approved by default - could potentially be an issue, but unlikely given ownership has to be confirmed for tier 2)
# (ii) reset the indexing defaults to be those of the lower tier 
# Tier 3 expiry:
# As per tier 2 expiry, with the addition of sending an email
def expire_listings(tier):
    new_tier = tier - 1
    expired_listings = []
    logger = logging.getLogger()
    try:
        conn = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_password)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        logger.debug('Looking for expired tier {} domains'.format(tier,))
        cursor.execute(sql_select_expired_listings, (tier,))
        results = cursor.fetchall()
        for result in results:
            expired_listing = {}
            expired_listing['domain'] = result['domain']
            if result['email']: expired_listing['email'] = result['email']
            expired_listings.append(expired_listing)
        if expired_listings:
            for expired_listing in expired_listings:
                logger.info('Expiring the following tier {} listing: {}'.format(tier, expired_listing['domain']))
                if tier == 1:
                    cursor.execute(sql_expire_tier1_listing, (expired_listing['domain'], expired_listing['domain']))
                    solr_delete_domain(expired_listing['domain'])
                elif tier == 2 or tier == 3:
                    cursor.execute(sql_expire_tier2or3_listing, (expired_listing['domain'], tier, expired_listing['domain'], new_tier, new_tier,))
                    cursor.execute(sql_reset_indexing_defaults, (new_tier, expired_listing['domain'],))
                    if tier == 3 and expired_listing['email']:
                        subject = "searchmysite.net Full listing expiry"
                        text = 'Dear {},\n\n'.format(expired_listing['email'])
                        text += 'Thank you for subscribing {} to searchmysite.net. I hope you have found it useful.\n\n'.format(expired_listing['domain'])
                        text += 'Unfortunately, your subscription has now expired, and your Full listing has reverted to a Free Trial listing. '
                        #text += 'This means that you can still log on, and still use the API, for the time being. '
                        text += 'If you would like to continue using the search as a service, you will need to resubscribe. '
                        text += 'While the Free Trial listing is active you can do this by simply going to https://searchmysite.net/admin/manage/subscriptions/ and selecting Purchase. '
                        text += 'Once the Free Trial expires, you will need to renew via Add Site (although you will not need to verify ownership of your site again).\n\n'
                        text += 'If you have any questions or comments, please don\'t hesitate to reply.\n\n'
                        text += 'Regards,\n\nsearchmysite.net\n\n'
                        # Currently using:
                        # success_status = send_email(None, None, subject, text)
                        # This is so it defaults to sending to admin. Once a few emails have been successfully sent, this should be changed to   
                        # success_status = send_email(None, expired_listing['email'], subject, text)
                        # so that the emails go direct to the users
                        success_status = send_email(None, None, subject, text)
                        if not success_status:
                            logger.error('Error sending email')
                conn.commit()
    except psycopg2.Error as e:
        logger.error('expire_unverified_sites: {}'.format(e.pgerror))
    finally:
        conn.close()
    return expired_listings


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

# Find all the pages in the site which have already been indexed (used for identifying pages which haven't already been indexed)
def get_already_indexed_links(domain):
    already_indexed_links = []
    solrquery = solr_query_to_get_already_indexed_links.format(domain)
    connection = urlopen(solr_url + solrquery)
    results = json.load(connection)
    if results['response']['docs']:
        for doc in results['response']['docs']:
            url = doc['url']
            if url:
                already_indexed_links.append(url)
    return already_indexed_links

# Get all the content for a domain
# Used for (i) identifying whether content has changed, and (ii) preserving existing content_chunks if the content hasn't changed
# Data structure is a dict of dicts, with the first dict keyed on id for easy retrieval,
# and the second dict using the docs structure returned by Solr.
# 'content', 'content_last_modified' and 'content_chunks' are all optional, and 'content_chunks' a list of dicts.
# e.g. 
# {
#   "https://michael-lewis.com/": 
#    {
#      "id":"https://michael-lewis.com/",
#      "url":"https://michael-lewis.com/",
#      "relationship":"parent",
#      "content":"...",
#      "content_last_modified":"...",
#      "content_chunks": 
#      [
#        {
#          "id":"https://michael-lewis.com/!chunk01",
#          "url":"https://michael-lewis.com/",
#          "relationship":"child",
#          "content_chunk_no":1,
#          "content_chunk_text":"..."
#        },
#        {
#          ...
#        }
#      ]
#   }
# }
def get_contents(domain):
    contents = {}
    solrquery = solr_query_to_get_content.format(domain)
    connection = urlopen(solr_url + solrquery)
    results = json.load(connection)
    if results['response']['docs']:
        for doc in results['response']['docs']:
            if 'id' in doc:
                contents[doc['id']] = doc
    return contents


# Database and Solr utils
# -----------------------

# Get web_feed and sitemap
# This takes as input a list of items from the current indexing job, 
# calculates the web_feed_auto_discovered and sitemap_auto_discovered values based on this and saves in the database,
# then determines which values to return for the web_feed and sitemap attributes stored in the Solr index
# Notes: 
# 1. The web_feed is the last XML content type which isn't named sitemap.xml, and the sitemap is the last
#    which is named sitemap.xml. This isn't robust because e.g. it doesn't inspect the content to confirm if it 
#    is an RSS or Atom feed (the content is not available at this stage), and doesn't look in robots.txt for the sitemap 
#    which might not be called sitemap.xml (again this is long after robots.txt is loaded). 
#    The item['content_type'][-3:] == 'xml' will find text/xml, application/xml, application/rss+xml, application/atom+xml.
# 2. If there's a *_user_entered it'll return that for Solr, otherwise if there's a *_auto_discovered it'll use that.
# 3. It is the only part of the indexing process which writes data discovered from indexing directly to tblDomains -
#    all other indexed data is saved to the Solr index. This is so that Solr just has 1 value for web_feed rather than 2, 
#    simplifying the searching logic.

def web_feed_and_sitemap(domain, items):
    preferred_feeds = ['/posts/index.xml', '/feed/', '/feed', '/feed.xml', '/feed/rss', '/feeds/all.xml', '/feeds/all.atom.xml', '/blog/atom', '/blog/atom.xml', '/blog/index.xml', '/blog/feed.xml', '/blog?format=rss', '/blog/feeds/all.xml', '/notes/index.xml', '/index.xml', '/atom.xml', '/rss.xml', '/rss']
    logger = logging.getLogger()
    web_feed = None
    sitemap = None
    web_feed_auto_discovered = None
    sitemap_auto_discovered = None
    web_feed_user_entered = None
    sitemap_user_entered = None
    try:
        # Step 1: Get the user entered values from the database
        conn = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_password)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_select_user_entered, (domain,))
        result = cursor.fetchone()
        if result['web_feed_user_entered']: web_feed_user_entered = result['web_feed_user_entered']
        if result['sitemap_user_entered']: sitemap_user_entered = result['sitemap_user_entered']
        # Step 2: Calculate the new system generated values from the items in the current indexing job
        web_feeds = []
        for item in items:
            if 'is_web_feed' in item:
                web_feed_auto_discovered = item['url']
                web_feeds.append(item['url'])
                del item['is_web_feed'] # Don't currently have an entry for this in the Solr schema so need to remove for now
            if item['content_type'] and len(item['content_type']) > 3 and item['url'] and len(item['url']) > 11:
                if item['content_type'][-3:] == 'xml':
                    if item['url'][-11:] == 'sitemap.xml':
                        sitemap_auto_discovered = item['url']
        # This iterates through the ordered preferred feeds list and checks against each of the discovered feeds. 
        # The first match that is found, i.e. the closest to the top of the preferred list, is selected.
        # If no feeds that match the preferred list, then the first is selected.
        if len(web_feeds) > 1:
            match_found = False
            for preferred_feed in preferred_feeds:
                for web_feed in web_feeds:
                    if web_feed.endswith(preferred_feed):
                        web_feed_auto_discovered = web_feed
                        match_found = True
                        break # break out of inner loop, i.e. for web_feed in web_feeds 
                if match_found:
                    break # break out of outer loop, i.e. for preferred_feed in preferred_feeds, if broken out of inner loop
            if match_found == True:
                logger.info('Multiple web feeds: {}. Choosing best match: {}'.format(web_feeds, web_feed_auto_discovered))
            else:
                web_feed_auto_discovered = web_feeds[0]
                logger.info('Multiple web feeds: {}. Choosing the first: {}'.format(web_feeds, web_feed_auto_discovered))
        # Step 3: Update the system generated values based on the current indexing job
        cursor.execute(sql_update_auto_discovered, (web_feed_auto_discovered, sitemap_auto_discovered, domain,))
        conn.commit()
        # Step 4: 
        if web_feed_user_entered:
            web_feed = web_feed_user_entered
        elif web_feed_auto_discovered:
            web_feed = web_feed_auto_discovered
        if sitemap_user_entered:
            sitemap = sitemap_user_entered
        elif sitemap_auto_discovered:
            sitemap = sitemap_auto_discovered
    except psycopg2.Error as e:
        logger.error(' %s' % e.pgerror)
    finally:
        conn.close()
    return web_feed, sitemap


# Domain utils
# ------------

# Extract domain from a URL, where domain could be a subdomain if that domain allows subdomains
# This is a variant of ../../web/content/dynamic/searchmysite/adminutils.py which takes domains_allowing_subdomains as an input parameter
# because don't want a database lookup every time this is called in this context
def extract_domain_from_url(url, domains_allowing_subdomains):
    # returns subdomain, domain, suffix, is_private=True|False), also registered_domain (domain+'.'+suffix) and fqdn (subdomain+'.'+domain+'.'+suffix)
    tld = tldextract.extract(url) 
    domain = tld.registered_domain
    if tld.domain == 'localhost' and tld.suffix == '': # special case for localhost which has tld.registered_domain = ''
        domain = tld.domain
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


# Vector search utils
# -------------------

# Return the page content as a list of content chunks, each chunk a max chunk_size, with a max length of max_chunks 
def get_content_chunks(content, max_chunks, id, url, domain):
    logger = logging.getLogger()
    if content:
        logger.info("Generating embeddings for {}".format(url))
        content_chunks = []
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        chunks = text_splitter.split_text(content)
        for chunk in chunks[:max_chunks]:
            chunk_no = chunks.index(chunk) + 1
            content_chunk = {}
            content_chunk['id'] = "{}!chunk{:03d}".format(id, chunk_no) # e.g. https://michael-lewis.com/!chunk001
            content_chunk['url'] = url
            content_chunk['domain'] = domain
            content_chunk['relationship'] = "child"
            content_chunk['content_chunk_no'] = chunk_no
            content_chunk['content_chunk_text'] = chunk
            content_chunk['content_chunk_vector'] = get_vector(chunk)
            if content_chunk['content_chunk_vector']:
                content_chunks.append(content_chunk)
            else:
                logger.warn("Unable to generate chunk number {} for {}".format(chunk_no, url))
    else:
        logger.info("Skipping embeddings for {} (no content)".format(url))
        content_chunks = None
    return content_chunks

# Return the embedding for the text as a list (i.e. in the format requried for Solr) 
def get_vector(text):
    logging.getLogger("sentence_transformers.SentenceTransformer").setLevel(logging.WARNING)
    model = SentenceTransformer(embedding_model)
    embedding = model.encode(text)
    vector = embedding.tolist()
    return vector


# Wikipedia utils
# ---------------

# Get latest completed import date
# Assumes the log status is "COMPLETE" and message of the format "Using export: 20210927"
def get_latest_completed_wikipedia_import(domain):
    completed_import_date = ""
    try:
        conn = psycopg2.connect(host=db_host, dbname=db_name, user=db_user, password=db_password)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute(sql_select_indexing_log, (domain, ))
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


# Email utils
# -----------

# reply_to_email and to_email optional.
# If reply_to_email None no Reply-To header set, and if to_email None then smtp_to_email env variable is used
# IMPORTANT: This function is in both indexing/common/utils.py and web/content/dynamic/searchmysite/util.py
# so if it is updated in one it should be updated in the other
def send_email(reply_to_email, to_email, subject, text): 
    success = True
    if not to_email:
        recipients = [smtp_to_email]
    else:
        recipients = [to_email, smtp_to_email]
    context = ssl.create_default_context()
    try:
        message = MIMEMultipart()
        message["From"] = smtp_from_email
        message["To"] = recipients[0]
        if reply_to_email:
            message['Reply-To'] = reply_to_email
        message["CC"] = smtp_to_email # Always cc the smtp_to_email env variable
        message["Subject"] = subject
        message.attach(MIMEText(text, "plain"))
        server = smtplib.SMTP(smtp_server, smtp_port)
        #server.set_debuglevel(1)
        server.starttls(context=context) # Secure the connection
        server.login(smtp_from_email, smtp_from_password)
        server.sendmail(smtp_from_email, recipients, message.as_string())
    except Exception as e:
        success = False
        #current_app.logger.error('Error sending email: {}'.format(e))
        logger = logging.getLogger()
        logger.error('Error sending email: {}'.format(e))
    finally:
        server.quit() 
    return success
