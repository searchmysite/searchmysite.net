import scrapy
from twisted.internet import reactor
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging
from scrapy.utils.project import get_project_settings
import logging
import psycopg2
import psycopg2.extras
from urllib.request import urlopen
import json
from indexer.spiders.search_my_site_script import SearchMySiteScript
from common.utils import update_indexing_log, get_all_domains, get_domains_allowing_subdomains, get_all_indexed_inlinks_for_domain


# As per https://docs.scrapy.org/en/latest/topics/practices.html
# This runs the SearchMySiteScript directly rather than via 'scrapy crawl' at the command line
# CrawlerProcess will start a Twisted reactor for you
# CrawlerRunner "provides more control over the crawling process" but
# "the reactor should be explicitly run after scheduling your spiders" and 
# "you will also have to shutdown the Twisted reactor yourself after the spider is finished"

settings = get_project_settings()
configure_logging(settings) # Need to pass in settings to pick up LOG_LEVEL, otherwise it will stay at DEBUG irrespective of LOG_LEVEL in settings.py
logger = logging.getLogger()

# Initialise variables

urls_to_crawl = []
# Just lookup domains_for_indexed_links and domains_allowing_subdomains once
domains_for_indexed_links = get_all_domains()
domains_allowing_subdomains = get_domains_allowing_subdomains()
common_config = {}

logger.debug('BOT_NAME: {} (indexer if custom settings are loaded okay, scrapybot if not)'.format(settings.get('BOT_NAME')))

db_name = settings.get('DB_NAME')
db_user = settings.get('DB_USER')
db_host = settings.get('DB_HOST')
db_password = settings.get('DB_PASSWORD')

filters_sql = "SELECT * FROM tblIndexingFilters WHERE domain = (%s);"

# This returns sites which are due for reindexing, either due to being new ('PENDING') 
# or having been last indexed more than indexing_frequency ago.
# Must also have indexing_type = 'spider/default' and indexing_enabled = TRUE
# Only LIMIT results are returned to reduce the chance of memory issues in the indexing container.
# The list is sorted so new ('PENDING') are first, followed by owner_verified,
# i.e. so these are prioritised in cases where not all sites are returned due to the LIMIT.
sql_to_get_domains_to_index = "SELECT domain, home_page, date_domain_added, indexing_page_limit, owner_verified, site_category, api_enabled FROM tblDomains "\
    "WHERE indexing_type = 'spider/default' "\
    "AND indexing_enabled = TRUE "\
    "AND (indexing_current_status = 'PENDING' OR (indexing_current_status = 'COMPLETE' AND now() - indexing_status_last_updated > indexing_frequency)) "\
    "ORDER BY indexing_current_status DESC, owner_verified DESC "\
    "LIMIT 16;"

sql_to_check_for_stuck_jobs = "SELECT * FROM tblDomains "\
    "WHERE indexing_type = 'spider/default' "\
    "AND indexing_current_status = 'RUNNING' "\
    "AND indexing_status_last_updated + '6 hours' < NOW();"

solrurl = settings.get('SOLR_URL')
solr_query_to_get_indexed_outlinks = "select?q=*%3A*&fq=indexed_outlinks%3A*{}*&fl=url,indexed_outlinks&rows=10000"

# Maintenance jobs
# This could be in a separately scheduled job, which could be run less frequently, but is just here for now to save having to setup another job
# The code to check for and action expired domains could go here too
try:
    conn = psycopg2.connect(dbname=db_name, user=db_user, host=db_host, password=db_password)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_to_check_for_stuck_jobs)
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

# Read data from database (urls_to_crawl, domains_for_indexed_links, exclusion for each urls_to_crawl)

logger.info('Checking for sites to index')

logger.debug('Reading from database {}'.format(db_name))
try:
    conn = psycopg2.connect(dbname=db_name, user=db_user, host=db_host, password=db_password)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    # urls_to_crawl
    cursor.execute(sql_to_get_domains_to_index)
    results = cursor.fetchall()
    for result in results:
        # Mark as RUNNING ASAP so if there's another indexer container running it is less likely to double-index 
        # There's a risk something will fail before it gets to the actual indexing, hence the periodic check for stuck RUNNING jobs
        update_indexing_log(result['domain'], 'RUNNING' , "")
        url = {}
        url['domain'] = result['domain']
        url['home_page'] = result['home_page']
        url['date_domain_added'] = result['date_domain_added']
        url['indexing_page_limit'] = result['indexing_page_limit']
        url['owner_verified'] = result['owner_verified']
        url['site_category'] = result['site_category']
        url['api_enabled'] = result['api_enabled']
        urls_to_crawl.append(url)
    if urls_to_crawl: logger.info('urls_to_crawl: {}'.format(urls_to_crawl))
    else: logger.debug('urls_to_crawl: {}'.format(urls_to_crawl))
    # domains_for_indexed_links
    if urls_to_crawl:
        common_config['domains_for_indexed_links'] = domains_for_indexed_links
    # domains allowing subdomains
    if urls_to_crawl:
        common_config['domains_allowing_subdomains'] = domains_allowing_subdomains
    # exclusions for domains
    if urls_to_crawl:
        for url_to_crawl in urls_to_crawl:
            cursor.execute(filters_sql, (url_to_crawl['domain'],))
            filters = cursor.fetchall()
            exclusions = []
            for f in filters:
                if f['action'] == 'exclude': # Only handle exclusions at the moment
                    exclusion = {}
                    exclusion['exclusion_type'] = f['type']
                    exclusion['exclusion_value'] = f['value']
                    exclusions.append(exclusion)
            url_to_crawl['exclusions'] = exclusions
except psycopg2.Error as e:
    logger.error(' %s' % e.pgerror)
finally:
    conn.close()

# Read data from Solr (indexed_inlinks)

for url_to_crawl in urls_to_crawl:
    indexed_inlinks = get_all_indexed_inlinks_for_domain(url_to_crawl['domain'])
    logger.debug('indexed_inlinks: {}'.format(indexed_inlinks))
    url_to_crawl['indexed_inlinks'] = indexed_inlinks

# Run the crawler

if urls_to_crawl:
    runner = CrawlerRunner(settings)
    for url_to_crawl in urls_to_crawl:
        runner.crawl(SearchMySiteScript, 
        site_config=url_to_crawl, common_config=common_config 
        )
    d = runner.join()
    d.addBoth(lambda _: reactor.stop())

    # Actually run the indexing
    logger.info('Starting indexing')
    reactor.run()
    logger.info('Completed indexing')