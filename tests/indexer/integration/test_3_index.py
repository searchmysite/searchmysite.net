import pytest
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.log import configure_logging
from scrapy.utils.project import get_project_settings
import logging
from indexer.spiders.search_my_site_script import SearchMySiteScript

#configure_logging(settings)
#logger = logging.getLogger()

#To execute the Scrapy tests:
#```
#export PYTHONPATH=~/projects/searchmysite/src/indexer
#export SCRAPY_SETTINGS_MODULE=indexer.settings
#pytest -v indexer/integration/test_3_index.py
#```

# Note: this currently returns PASSED, but with a logging error.
# Also, there isn't an assert to check for a return value or state, so just going to 
# docker exec -it src_indexer_1 python /usr/src/app/search_my_site_scheduler.py
# for now

def test_index(site_details):
    # search_my_site_scheduler.py:
    #runner = CrawlerRunner(settings)
    #for url_to_crawl in urls_to_crawl:
    #    runner.crawl(SearchMySiteScript, 
    #    site_config=url_to_crawl, common_config=common_config 
    #)
    #d = runner.join()
    #d.addBoth(lambda _: reactor.stop())
    #reactor.run()
    # class SearchMySiteScript(CrawlSpider):
    #self.site_config = kwargs.get('site_config')
    #self.common_config = kwargs.get('common_config')
    #self.start_url = self.site_config['home_page']
    #self.domain = self.site_config['domain']
    #self.exclusions = self.site_config['exclusions']
    #self.domains_for_indexed_links = self.common_config['domains_for_indexed_links']
    common_config = {}
    common_config['domains_for_indexed_links'] = [domain]
    common_config['domains_allowing_subdomains'] = []
    urls_to_crawl = []
    url = {}
    url['domain'] = pytest.site_domain
    url['home_page'] = pytest.site_home_page
    #url['date_domain_added'] = result['date_domain_added']
    #url['indexing_page_limit'] = result['indexing_page_limit']
    #url['owner_verified'] = result['owner_verified']
    url['site_category'] = pytest.site_category
    #url['api_enabled'] = result['api_enabled']
    urls_to_crawl.append(url)
    process = CrawlerProcess(settings)
    process.crawl(SearchMySiteScript)

