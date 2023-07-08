import scrapy
from twisted.internet import reactor
from scrapy.crawler import CrawlerRunner
from scrapy.utils.log import configure_logging
from scrapy.utils.project import get_project_settings
import logging
import psycopg2
import psycopg2.extras
from indexer.spiders.search_my_site_spider import SearchMySiteSpider
from common.utils import update_indexing_status, get_all_domains, get_domains_allowing_subdomains, get_all_indexed_inlinks_for_domain, get_already_indexed_links, get_contents, check_for_stuck_jobs, expire_listings


# As per https://docs.scrapy.org/en/latest/topics/practices.html
# This runs the SearchMySiteSpider directly rather than via 'scrapy crawl' at the command line
# CrawlerProcess will start a Twisted reactor for you
# CrawlerRunner "provides more control over the crawling process" but
# "the reactor should be explicitly run after scheduling your spiders" and 
# "you will also have to shutdown the Twisted reactor yourself after the spider is finished"

settings = get_project_settings()
configure_logging(settings) # Need to pass in settings to pick up LOG_LEVEL, otherwise it will stay at DEBUG irrespective of LOG_LEVEL in settings.py
logger = logging.getLogger()

# Initialise variables
# - sites_to_crawl and common_config are the two values passed into SearchMySiteSpider
# - sites_to_crawl is a list of dicts, where each dict in the list corresponds to a site which needs to be crawled,
#   and the dict contains all the information about the site which could be needed at index time, e.g.
#   - site['site_category']
#   - site['web_feed']
#   - site['exclusions'] (a list of dicts)
#   - site['indexed_inlinks'] (from Solr)
#   - site['content'] (from Solr)
#   - site['already_indexed_links'] (from Solr, only set for incremental indexes)
# - common_config is a dict with settings which apply to all sites, i.e.
#   - common_config['domains_for_indexed_links']
#   - common_config['domains_allowing_subdomains']
 
sites_to_crawl = []
# Just lookup domains_for_indexed_links and domains_allowing_subdomains once
domains_for_indexed_links = get_all_domains()
domains_allowing_subdomains = get_domains_allowing_subdomains()
common_config = {}

logger.debug('BOT_NAME: {} (indexer if custom settings are loaded okay, scrapybot if not)'.format(settings.get('BOT_NAME')))

db_name = settings.get('DB_NAME')
db_user = settings.get('DB_USER')
db_host = settings.get('DB_HOST')
db_password = settings.get('DB_PASSWORD')

sql_select_filters = "SELECT * FROM tblIndexingFilters WHERE domain = (%s);"

# This returns sites which are due for reindexing, either due to being new ('PENDING'), 
# or having the last full index completed more than full_reindex_frequency ago, or
# having the last index of any type (full or incremental) completed more than incremental_reindex_frequency ago.
# Must also have indexing_type = 'spider/default' and indexing_enabled = TRUE.
# Only LIMIT results are returned to reduce the chance of memory issues in the indexing container.
# The list is sorted so new ('PENDING') are first, followed by higher tiers,
# so these are prioritised in cases where not all sites are returned due to the LIMIT.
# The CASE statement sets a column full_index to be TRUE when a full index is required
# and FALSE when an incremental index is required. In cases where both a full and 
# incremental index are due to be triggered the full index will come first.
sql_select_domains_to_index = "SELECT d.domain, d.home_page, l.tier, d.domain_first_submitted, d.indexing_page_limit, d.content_chunks_limit, d.category, d.api_enabled, d.include_in_public_search, d.web_feed_auto_discovered, d.web_feed_user_entered, "\
    "    CASE "\
    "        WHEN d.indexing_status = 'PENDING' THEN TRUE "\
    "        WHEN NOW() - d.last_full_index_completed > d.full_reindex_frequency THEN TRUE "\
    "        WHEN NOW() - d.last_index_completed > d.incremental_reindex_frequency THEN FALSE "\
    "    END AS full_index "\
    "FROM tblDomains d INNER JOIN tblListingStatus l ON d.domain = l.domain "\
    "WHERE d.indexing_type = 'spider/default' "\
    "AND d.indexing_enabled = TRUE "\
    "AND (d.indexing_status = 'PENDING') "\
    "    OR (d.indexing_status = 'COMPLETE' AND NOW() - last_full_index_completed > full_reindex_frequency) "\
    "    OR (d.indexing_status = 'COMPLETE' AND NOW() - last_index_completed > incremental_reindex_frequency) "\
    "ORDER BY d.indexing_status DESC, l.tier DESC "\
    "LIMIT 16;"


# MAINTENANCE JOBS
# These could be in a separately scheduled job, which could be run less frequently, but is just here for now to save having to setup another job
check_for_stuck_jobs()
for tier in range(1, 4):
    expire_listings(tier) # i.e. expire any tier 1 listings that are due for expiry, then tier 2, then tier 3


# MAIN INDEXING JOB
# Read data from database (sites_to_crawl, domains_for_indexed_links, exclusion for each sites_to_crawl)

logger.info('Checking for sites to index')

logger.debug('Reading from database {}'.format(db_name))
try:
    conn = psycopg2.connect(dbname=db_name, user=db_user, host=db_host, password=db_password)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    # sites_to_crawl is the config specific to each site
    cursor.execute(sql_select_domains_to_index)
    results = cursor.fetchall()
    for result in results:
        # Mark as RUNNING ASAP so if there's another indexer container running it is less likely to double-index 
        # There's a risk something will fail before it gets to the actual indexing, hence the periodic check for stuck RUNNING jobs
        update_indexing_status(result['domain'], None, 'RUNNING' , "")
        site = {}
        site['domain'] = result['domain']
        site['home_page'] = result['home_page']
        site['tier'] = result['tier']
        site['date_domain_added'] = result['domain_first_submitted']
        site['indexing_page_limit'] = result['indexing_page_limit']
        site['content_chunks_limit'] = result['content_chunks_limit']
        if result['tier'] == 3: site['owner_verified'] = True
        else: site['owner_verified'] = False
        site['site_category'] = result['category']
        site['api_enabled'] = result['api_enabled']
        site['include_in_public_search'] = result['include_in_public_search']
        # Use web_feed_user_entered if there is one, otherwise use web_feed_auto_discovered
        if result['web_feed_user_entered']: 
            site['web_feed'] = result['web_feed_user_entered']
        elif result['web_feed_auto_discovered']:
            site['web_feed'] = result['web_feed_auto_discovered']
        site['full_index'] = result['full_index']
        sites_to_crawl.append(site)
    if sites_to_crawl: logger.info('sites_to_crawl: {}'.format(sites_to_crawl))
    else: logger.debug('sites_to_crawl: {}'.format(sites_to_crawl))
    # common_config is the config shared between all sites
    if sites_to_crawl:
        # domains_for_indexed_links
        common_config['domains_for_indexed_links'] = domains_for_indexed_links
        # domains allowing subdomains
        common_config['domains_allowing_subdomains'] = domains_allowing_subdomains
        # exclusions for domains
        for site_to_crawl in sites_to_crawl:
            cursor.execute(sql_select_filters, (site_to_crawl['domain'],))
            filters = cursor.fetchall()
            exclusions = []
            for f in filters:
                if f['action'] == 'exclude': # Only handle exclusions at the moment
                    exclusion = {}
                    exclusion['exclusion_type'] = f['type']
                    exclusion['exclusion_value'] = f['value']
                    exclusions.append(exclusion)
            site_to_crawl['exclusions'] = exclusions
except psycopg2.Error as e:
    logger.error(' %s' % e.pgerror)
finally:
    conn.close()

# Read data from Solr (indexed_inlinks, content and if necessary already_indexed_links)

for site_to_crawl in sites_to_crawl:
    # indexed_inlinks, i.e. pages (from other domains within this search index) which link to this domain.
    indexed_inlinks = get_all_indexed_inlinks_for_domain(site_to_crawl['domain'])
    logger.debug('indexed_inlinks: {}'.format(indexed_inlinks))
    site_to_crawl['indexed_inlinks'] = indexed_inlinks
    # content, i.e. get_contents(domain)
    contents = get_contents(site_to_crawl['domain'])
    logger.debug('contents: {}'.format(contents.keys))
    site_to_crawl['contents'] = contents
    # already_indexed_links, i.e. pages on this domain which have already been indexed.
    # This is only set if it is needed, i.e. for an incremental index.
    if site['full_index'] == False: 
        already_indexed_links = get_already_indexed_links(site_to_crawl['domain'])
        no_of_already_indexed_links = len(already_indexed_links)
        indexing_page_limit = site_to_crawl['indexing_page_limit']
        if no_of_already_indexed_links == indexing_page_limit:
            # if the indexing_page_limit was reached in the last index then abandon this index
            # update the status in the database so that it isn't selected again until the next scheduled full or incremental reindex
            sites_to_crawl.remove(site_to_crawl)
            message = 'The indexing page limit was reached on the last index, so not going to perform incremental reindex for {}'.format(site_to_crawl['domain'])
            update_indexing_status(site_to_crawl['domain'], site['full_index'], 'COMPLETE' , message)
            logger.warning(message)
        else:
            # reduce the indexing_page_limit according to the number of pages already in the index
            # so the incremental reindex doesn't exceed the indexing_page_limit
            new_indexing_page_limit = indexing_page_limit - no_of_already_indexed_links
            site_to_crawl['indexing_page_limit'] = new_indexing_page_limit
            logger.info('no_of_already_indexed_links: {}, indexing_page_limit: {}, new_indexing_page_limit: {}, for {}'.format(no_of_already_indexed_links, indexing_page_limit, new_indexing_page_limit, site_to_crawl['domain']))
            site_to_crawl['already_indexed_links'] = already_indexed_links

# Run the crawler

if sites_to_crawl:
    runner = CrawlerRunner(settings)
    for site_to_crawl in sites_to_crawl:
        runner.crawl(SearchMySiteSpider, 
        site_config=site_to_crawl, common_config=common_config 
        )
    d = runner.join()
    d.addBoth(lambda _: reactor.stop())

    # Actually run the indexing
    logger.info('Starting indexing')
    reactor.run()
    logger.info('Completed indexing')
