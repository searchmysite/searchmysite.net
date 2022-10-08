import scrapy
from scrapy.spiders import Spider, CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor, IGNORED_EXTENSIONS
from scrapy.exceptions import CloseSpider, IgnoreRequest
from scrapy.http.response.text import TextResponse
from scrapy.http import Request, HtmlResponse, XmlResponse
from scrapy.utils.log import configure_logging
from scrapy.utils.project import get_project_settings
import logging
from bs4 import BeautifulSoup
import datetime
from urllib.parse import urlsplit
import feedparser
from indexer.spiders.search_my_site_parser import customparser
import re

# extensions which have caused issues
IGNORED_EXTENSIONS += ['jar', 'json', 'cbr'] 

class SearchMySiteSpider(CrawlSpider):
    name = "searchmysitespider"

    custom_settings = {
        'ITEM_PIPELINES': {
            'indexer.pipelines.SolrPipeline': 300
        }
    }

    def __init__(self, *args, **kwargs):
        # Get kwargs
        self.site_config = kwargs.get('site_config')
        self.common_config = kwargs.get('common_config')
        self.domain = self.site_config['domain']
        self.home_page = self.site_config['home_page']
        if 'web_feed' in self.site_config.keys():
            self.web_feed = self.site_config['web_feed']
        else:
            self.web_feed = None
        self.full_index = self.site_config['full_index'] 
        self.logger.debug('Full index {}'.format(self.full_index))
        self.exclusions = self.site_config['exclusions']
        self.domains_for_indexed_links = self.common_config['domains_for_indexed_links']
        self.site_config['feed_links'] = [] # This will be instantiated by parse_start_url
        # Need to remove current domain from the list so indexed_outlinks does just contain outlinks
        # (and also check the current domain is in the list in case it has been removed for another domain allowing subdomains)
        if self.domain in self.domains_for_indexed_links: self.domains_for_indexed_links.remove(self.domain)
        # Set Scrapy spider attributes, i.e. start_urls and allowed_domains
        # start_urls is where the indexing starts, in this case the home page and (if present) web feed
        if self.web_feed:
            self.start_urls = [self.home_page, self.web_feed]
        else:
            self.start_urls = [self.home_page]
        self.allowed_domains = [self.domain]
        self.logger.info('Start URLs {}'.format(self.start_urls))
        self.logger.info('Allowed domains {}'.format(self.allowed_domains))
        self.logger.debug('Domains for indexed_outlinks {}'.format(self.domains_for_indexed_links))
        # Set up deny list
        # Adding the pinterest and tumblr deny rules to prevent urls such as the following being indexed e.g. for example.com
        # https://www.pinterest.com/pin/create/button/?url=https%3A%2F%2Fexample.com...
        # https://www.tumblr.com/widgets/share/tool/preview?shareSource=legacy&canonicalUrl=&url=https%3A%2F%2Fexample.com%2F
        # These seem to be triggered by links on the original domain such as
        # https://example.com/page/?share=pinterest
        deny = [r'.*\?share\=pinterest.*', r'.*\?share\=tumblr.*']
        for exclusion in self.exclusions:
            if exclusion['exclusion_type'] == 'path':
                exclusion_value = exclusion['exclusion_value']
                if '*.' in exclusion_value: # A *. in the deny parameter on LinkExtractor seems to block all indexing so need to find and replace with a safe alternative
                    old_exclusion_value = exclusion_value
                    exclusion_value = re.sub('^\*\.(\w+)$', r'.\1$', exclusion_value) # replace e.g. '*.xml' with '.xml$', '*.json' with '.json$' etc.
                    self.logger.info('Changing {} in deny path to {}'.format(old_exclusion_value, exclusion_value))
                deny.append(exclusion_value)
        self.logger.info('Deny path {}'.format(deny))
        # Common rules are to only index pages on the same domain, deny paths as above, use an extended IGNORED_EXTENSIONS list as above,
        # and add link to the tags to pick up RSS feeds from <link rel="alternate" type="application/rss+xml" href=
        # There are two key differences if it is not a full index:
        # 1. Only index new links, i.e. links which aren't already in the index (use process_links to remove 
        #    already indexed links from the home_page links and parse_start_url to remove already indexed links
        #    from the rss_feed and sitemap links).
        # 2. Do not follow links, i.e. only index the new links on the home page, rss_feed and sitemap. 
        if self.full_index == True:
            self.rules = (
                Rule(
                    LinkExtractor(allow_domains=self.allowed_domains, deny=deny, deny_extensions=IGNORED_EXTENSIONS, tags=('a','area','link')),
                    callback=self.parse_item, follow=True
                    ),
                )
        else:
            self.rules = (
                Rule(
                    LinkExtractor(allow_domains=self.allowed_domains, deny=deny, deny_extensions=IGNORED_EXTENSIONS, tags=('a','area','link')),
                    callback=self.parse_item, process_links=self.remove_already_indexed_links, follow=False
                    ),
                )
        super(SearchMySiteSpider, self).__init__(self, *args, **kwargs)

    # parse_start_url is called for each of the start_urls
    # It serves two important purposes:
    # 1. Sets the is_home attribute for the home page. It is vital that this is set for one page in the site
    #    otherwise that site won't appear on the Browse page. We can't use response.url = home_page because some
    #    sites redirect the home page. We also need to parse the home here because otherwise it'll be skipped.
    #    Note: It is assumed there is only one URL in start_urls which returns an HtmlResponse and that this is
    #    the home page.
    # 2. Parses the web_feed for links. They don't have their links extracted by the LinkExtractor Rule
    #    because the LinkExtractor Rule only works where the response is an HtmlResponse (web_feed
    #    is an XmlResponse).
    def parse_start_url(self, response):
        configure_logging(get_project_settings())
        logger = logging.getLogger()
        if isinstance(response, XmlResponse) and response.url == self.web_feed:
            logger.info('Processing web feed: {}'.format(response.url))
            d = feedparser.parse(response.text)
            entries = d.entries
            version = None
            no_of_links = None
            # if the url isn't a valid feed, d.entries will succeed with None, but d.version will raise a
            # AttributeError: object has no attribute 'version'
            if entries:
                version = d.version
                for entry in entries:
                    if 'link' in entry:
                        self.site_config['feed_links'].append(entry.link)
            if self.full_index == True:
                # Index all links on full index
                links_to_index = self.site_config['feed_links']
            else: 
                # Only index new links on incremental index, i.e. remove seen links
                links_to_index = [link for link in self.site_config['feed_links'] if link not in self.site_config['already_indexed_links']]
            logger.info('Web feed version: {}, total links: {}, total links to index: {}'.format(version, len(self.site_config['feed_links']), len(links_to_index)))
            #logger.debug('Links in web feed to index: {}'.format(links_to_index))
            # Also need to index the web feed itself
            # If this is not done, the web feed will not be processed by process_item in the pipeline and so the web_feed_auto_discovered will be removed in close_spider
            is_home = False
            item = customparser(response, self.domain, is_home, self.domains_for_indexed_links, self.site_config, self.common_config)
            yield item
            for link in links_to_index:
                yield Request(link, callback=self.parse_item)
        elif isinstance(response, HtmlResponse):
            logger.info('Processing home page: {}'.format(response.url))
            if self.full_index == True: # Only index the home page on full index
                is_home = True
                item = customparser(response, self.domain, is_home, self.domains_for_indexed_links, self.site_config, self.common_config)
                yield item
        else:
            logger.warn('Skipping processing start_url: {}'.format(response.url))

    def parse_item(self, response):
        configure_logging(get_project_settings())
        logger = logging.getLogger()
        logger.debug('Parsing URL: {}'.format(response.url))
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
            # If the page matches a type in the exclusion list, item will be None, so in that case don't yield item. 
            # This won't increment item_scraped_count
            if item:
                yield item

    # As per https://docs.scrapy.org/en/latest/topics/spiders.html the "default implementation generates Request(url, dont_filter=True) 
    # for each url in start_urls"
    # The dont_filter=True means that the start_urls bypass the deduplication, which means a 2nd home page could be indexed after the first, 
    # and the 2nd wouldn't have is_home=true, so we need to override this method
    def start_requests(self):
        for url in self.start_urls:
            yield Request(url)

    # remove_already_indexed_links is called by process_links in the LinkExtractor Rule
    # This means it is called for every HtmlResponse, but not for any XmlResponse.
    # From the start_urls, it is only called for the home_page, not web_feed which is an XmlResponse
    def remove_already_indexed_links(self, links):
        if 'already_indexed_links' in self.site_config.keys():
            for link in links:
                if link.url not in self.site_config['already_indexed_links']:
                    yield link
