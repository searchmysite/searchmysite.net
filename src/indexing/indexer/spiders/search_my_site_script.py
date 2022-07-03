import scrapy
from scrapy.spiders import Spider, CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor, IGNORED_EXTENSIONS
from scrapy.exceptions import CloseSpider, IgnoreRequest
from scrapy.http.response.text import TextResponse
from scrapy.http import Request
from scrapy.utils.log import configure_logging
from scrapy.utils.project import get_project_settings
import logging
from bs4 import BeautifulSoup
import datetime
from urllib.parse import urlsplit
from indexer.spiders.search_my_site_parser import customparser
import re

# extensions which have caused issues
IGNORED_EXTENSIONS += ['jar', 'json', 'cbr'] 

class SearchMySiteScript(CrawlSpider):
    name = "searchmysitescript"

    custom_settings = {
        'ITEM_PIPELINES': {
            'indexer.pipelines.SolrPipeline': 300
        }
    }

    def __init__(self, *args, **kwargs):
        # Get kwargs
        self.site_config = kwargs.get('site_config')
        self.common_config = kwargs.get('common_config')
        self.start_url = self.site_config['home_page']
        self.domain = self.site_config['domain']
        self.exclusions = self.site_config['exclusions']
        self.domains_for_indexed_links = self.common_config['domains_for_indexed_links']
        # Need to remove current domain from the list so indexed_outlinks does just contain outlinks
        self.domains_for_indexed_links.remove(self.domain)
        # Set Scrapy spider attributes, i.e. start_urls and allowed_domains
        self.start_urls = [self.start_url]
        self.allowed_domains = [self.domain]
        self.logger.info('Start URL {}'.format(self.start_urls))
        self.logger.info('Allowed domains {}'.format(self.allowed_domains))
        self.logger.debug('Domains for indexed_outlinks {}'.format(self.domains_for_indexed_links))
        # Set up deny list, if there are any 
        deny = []
        for exclusion in self.exclusions:
            if exclusion['exclusion_type'] == 'path':
                exclusion_value = exclusion['exclusion_value']
                if '*.' in exclusion_value: # A *. in the deny parameter on LinkExtractor seems to block all indexing so need to find and replace with a safe alternative
                    old_exclusion_value = exclusion_value
                    exclusion_value = re.sub('^\*\.(\w+)$', r'.\1$', exclusion_value) # replace e.g. '*.xml' with '.xml$', '*.json' with '.json$' etc.
                    self.logger.info('Changing {} in deny path to {}'.format(old_exclusion_value, exclusion_value))
                deny.append(exclusion_value)
        self.logger.info('Deny path {}'.format(deny))
        # Rules:
        # only index pages on the same domain
        # deny paths as per above
        # use an extended IGNORED_EXTENSIONS list which also includes jar etc. files
        # Might want to restrict indexing to sub pages of the home page at some point, 
        # e.g. if home is https://www.fieggen.com/shoelace/index.htm restrict to pages that start https://www.fieggen.com/shoelace/
        # this could potentially be implemented with a process_value rule

        self.rules = (
            Rule(
                LinkExtractor(allow_domains=self.allowed_domains, deny=deny, deny_extensions=IGNORED_EXTENSIONS), 
                callback="parse_item", follow=True
                ),
            )
        super(SearchMySiteScript, self).__init__(self, *args, **kwargs)

    def parse_start_url(self, response): # This is required so the start_url is actually parsed rather than skipped
        configure_logging(get_project_settings())
        logger = logging.getLogger()
        logger.info('Parsing start URL {}'.format(response.url))
        # Very important to ensure every site has a home page set or it won't appear on the Browse page.
        # Note that response.url here may be different from start_url if start_url redirects.
        is_home = True
        item = customparser(response, self.domain, is_home, self.domains_for_indexed_links, self.site_config, self.common_config)
        yield item

    def parse_item(self, response):
        configure_logging(get_project_settings())
        logger = logging.getLogger()
        scrape_count = self.crawler.stats.get_value('item_scraped_count')
        indexing_page_limit = self.site_config['indexing_page_limit']
        # Using this method to stop the spider when indexing_page_limit reached
        # Can't use self.settings['CLOSESPIDER_ITEMCOUNT'] because that is at class level, 
        # but we may have different values at instance level
        if scrape_count == indexing_page_limit:
            logger.info('Indexing page limit of {} reached.'.format(str(indexing_page_limit)))
            raise CloseSpider("Indexing page limit reached.")
        if not isinstance(response, TextResponse):
            logger.info('Item {} is not a TextResponse, so skipping.'.format(response)) # Skip item if e.g. an image
        else:
            is_home = False
            item = customparser(response, self.domain, is_home, self.domains_for_indexed_links, self.site_config, self.common_config)
            # If the page matches a type in the exclusion list, item will be None, so in that case don't yield item. This won't increment item_scraped_count
            if item:
                yield item

    # As per https://docs.scrapy.org/en/latest/topics/spiders.html the "default implementation generates Request(url, dont_filter=True) for each url in start_urls"
    # The dont_filter=True means that the start_urls bypass the deduplication, which means a 2nd home page could be indexed after the first, and the 2nd wouldn't have is_home=true
    # So we need to override this method
    def start_requests(self):
        for url in self.start_urls:
            yield Request(url)
