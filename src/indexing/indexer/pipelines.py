import pysolr
from scrapy.utils.log import configure_logging
from scrapy.exceptions import DropItem
import re
from scrapy.utils.log import configure_logging
from scrapy.utils.project import get_project_settings
import logging
from common.utils import update_indexing_status, get_last_complete_indexing_log_message, deactivate_indexing, web_feed_and_sitemap, convert_datetime_to_utc_date, send_email


# This is the Solr pipeline, for submitting indexed items to Solr
# It originally just did a self.solr.add(dict(item)) in process_item 
# and self.solr.commit() in close_spider because a commit on every add was slow.
# However, it now builds a list of dicts and only connects to Solr on the close_spider.
# 
# Notes on deduplication:
# If I start indexing https://michael-lewis.com/ from https://www.michael-lewis.com/ 
# I get the following duplicated entries:
# https://www.michael-lewis.com/ and https://michael-lewis.com/
# And if I index http://www.paulgraham.com/ I get duplicates for most of the pages, e.g.
# http://www.paulgraham.com/airbnb.html and http://paulgraham.com/airbnb.html
# The recommended way of doing deduplication according to https://docs.scrapy.org/en/latest/topics/settings.html#dupefilter-class
# is to do a DUPEFILTER_CLASS = 'indexer.custom_filters.SearchMySiteDupeFilter' and class SearchMySiteDupeFilter(RFPDupeFilter)
# in custom_filters.py (at the same level as settings.py) extending request_fingerprint.
# However, only the request object is available, and that makes a fingerprint of the request.url
# e.g. with w3lib.url.canonicalize_url, but (i) you can't reliably remove the www. from all pages 
# (a workaround could be to remove the whole domain and fingerprint on the path, but that would break
# if there were ever sites like blog.domain.com and news.domain.com), and (ii) I don't think you can 
# access previous request.urls for comparison.

class SolrPipeline:

    def __init__(self, stats, solr_url):
        self.solr_url = solr_url
        self.items = []
        configure_logging()
        self.logger = logging.getLogger()
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            solr_url = crawler.settings.get('SOLR_URL'),
            stats = crawler.stats
        )

    def open_spider(self, spider):
        self.solr = pysolr.Solr(self.solr_url) # always_commit=False by default
        return

    # close_spider is run for each site at the end of the spidering process
    # Depending on the type of index (full or incremental) and and the outcome
    # - If it is a full reindex, but zero documents have been found, that suggests an error somewhere, e.g. site unavailable.
    #   If that happens twice in a row, that suggests a more permanent error, so indexing for the site is deactivated.
    # - If it is a full reindex, but documents are found, get all the site specific data which is set on the hoem page,
    #   and clear out the exiting index for that site.
    # - If it is an incremental reindex, don't delete the existign docs, just add the new ones.
    def close_spider(self, spider):
        no_of_docs = len(self.items)
        if spider.site_config['full_index'] == True and no_of_docs == 0:
            self.logger.warning('No documents found at start urls {} (domain {}). This is likely an error with the site or with this system.'.format(spider.start_urls, spider.domain))
            message = 'WARNING: No documents found. '
            submessage = ''
            if self.stats.get_value('robotstxt/forbidden'):
                submessage = 'Likely robots.txt forbidden. '
            elif self.stats.get_value('retry/max_reached'):
                submessage = 'Likely site timeout. '
            last_message = get_last_complete_indexing_log_message(spider.domain)
            # For the first zero document error, don't delete the old docs, but if the listing is deactivated, then delete the existing docs.
            if last_message.startswith(message):
                tier = spider.site_config['tier']
                newmessage = 'The previous indexing for {} also found no documents. Deleting existing Solr docs and deactivating indexing.'.format(spider.domain)
                self.logger.warning(newmessage)
                self.solr.delete(q='domain:{}'.format(spider.domain))
                deactivate_indexing(spider.domain, "Indexing failed twice in a row. {}".format(submessage))
                message = message + submessage + newmessage
                if tier == 3: # If a paid for listing, send an email to the site admin for investigation
                    subject = "Tier 3 site indexing diabled"
                    success_status = send_email(None, None, subject, message)
                    if not success_status:
                       self.logger.error('Error sending email')
            else:
                message = message + submessage + 'robotstxt/forbidden {}, retry/max_reached {}'.format(self.stats.get_value('robotstxt/forbidden'), self.stats.get_value('retry/max_reached'))
        else:
            if spider.site_config['full_index'] == True:
                # Get values which are only set for the home page
                # Note that the home page will only be updated in a full reindex
                api_enabled = spider.site_config['api_enabled']
                date_domain_added = convert_datetime_to_utc_date(spider.site_config['date_domain_added'])
                web_feed, sitemap = web_feed_and_sitemap(spider.domain, self.items)
                self.logger.info('Using web_feed: {}, sitemap: {}'.format(web_feed, sitemap))
                # Delete the existing documents
                # It is important to delete all existing documents on a full reindex to clean up moved and deleted documents
                # but the delete all existing documents must only be performed for a full rather than incremental reindex
                self.logger.info('Deleting existing Solr docs for {}.'.format(spider.domain))
                self.solr.delete(q='domain:{}'.format(spider.domain))
                # Add the new documents
                self.logger.info('Full index, submitting {} newly spidered docs to Solr for {}.'.format(str(no_of_docs), spider.domain))
                for item in self.items:
                    # Add the values which are only set for the home page
                    if item['is_home'] == True:
                        self.logger.info('Home page URL {} has api_enabled {}, date_domain_added {}, and web_feed {}'.format(item['url'], api_enabled, date_domain_added, web_feed))
                        item['api_enabled'] = api_enabled
                        item['date_domain_added'] = date_domain_added
                        item['web_feed'] = web_feed
                    self.solr.add(dict(item))
            else:
                # i.e. if just an incremental index
                # Note that the first incremental index for a site must come after the first full index, to ensure the full index sets e.g. the home page values
                self.logger.info('Incremental index, submitting {} docs to Solr for {}.'.format(str(no_of_docs), spider.domain))
                for item in self.items:
                    # This is removed by web_feed_and_sitemap for a full index, so have to remove here for incremental otherwise Solr will return error
                    if 'is_web_feed' in item:
                        del item['is_web_feed'] 
                    self.solr.add(dict(item))
            # Save changes
            self.solr.commit()
            message = 'SUCCESS: {} documents found. '.format(self.stats.get_value('item_scraped_count'))
            if self.stats.get_value('log_count/WARNING'):
                message = message + 'log_count/WARNING: {} '.format(self.stats.get_value('log_count/WARNING'))
            if self.stats.get_value('log_count/ERROR'):
                message = message + 'log_count/ERROR: {} '.format(self.stats.get_value('log_count/ERROR'))
        # Update indexing status to mark as 'COMPLETE'.
        # Pass in whether full index or not (i.e. whether indexing type full or incremental) to set the appropriate completed times.
        # Message starts with SUCCESS or WARNING.
        update_indexing_status(spider.domain, spider.site_config['full_index'], 'COMPLETE', message)

    def process_item(self, item, spider):
        new_url = item['url']
        # Strip out the trailing slashes of the new for a fairer comparison
        # so e.g. https://michael-lewis.com/ and https://michael-lewis.com get treated as duplicates
        #if new_url.endswith('/'): new_url = new_url[:-1]
        new_title = item['title']
        add = True
        for i in self.items:
            existing_url = i['url']
            #if existing_url.endswith('/'): existing_url = existing_url[:-1]
            existing_title = i['title']
            # if new_url is the same as existing_url (this shouldn't happen because of built-in deduplication) or
            # if new_url without www. is the same as an existing_url or vice versa (which could happen because the built-in deduplication doesn't catch this)
            if new_url == existing_url or re.sub("www\.", "", new_url, 1) == existing_url or re.sub("www\.", "", existing_url, 1) == new_url:
                # double check with title, to increase chance of it being a genuine duplicate
                # could put more checks, e.g. keywords, but not sure about last_modified_date in case that is dynamic
                if new_title == existing_title:
                    add = False
                    self.logger.info("Not going to add {} because it is a duplicate of {}".format(new_url, existing_url))
        if add == True:
            self.logger.info("Adding {}".format(new_url))
            self.items.append(dict(item))
            return item
        else:
            raise DropItem("Duplicate: {}".format(new_url))
