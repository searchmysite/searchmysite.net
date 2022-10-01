import os
# -*- coding: utf-8 -*-

# Scrapy settings for indexer project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html


BOT_NAME = 'indexer'

SPIDER_MODULES = ['indexer.spiders']
NEWSPIDER_MODULE = 'indexer.spiders'

# Searchmysite custom config for database settings
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_NAME = 'searchmysitedb'
DB_USER = 'postgres'
DB_HOST = 'db'

SOLR_URL = 'http://search:8983/solr/content/'

LOG_LEVEL = 'INFO'

# Searchmysite custom dupe filter
#DUPEFILTER_CLASS = 'indexer.custom_filters.SearchMySiteDupeFilter'

# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = 'indexer (+http://www.yourdomain.com)'
USER_AGENT = 'Mozilla/5.0 (compatible; SearchMySiteBot/1.0; +https://searchmysite.net)'

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Configure maximum concurrent requests performed by Scrapy (default: 16)
CONCURRENT_REQUESTS = 16

# Configure a delay for requests for the same website (default: 0)
# See https://docs.scrapy.org/en/latest/topics/settings.html#download-delay
# See also autothrottle settings and docs
DOWNLOAD_DELAY = 2
# The download delay setting will honor only one of:
CONCURRENT_REQUESTS_PER_DOMAIN = 4
#CONCURRENT_REQUESTS_PER_IP = 16

# Default: 180 (seconds)
DOWNLOAD_TIMEOUT = 30

# Need to set this because large files like https://drwho.virtadpt.net/files/OMNI_1987_11.cbr were crashing production
# Default: 1073741824 (1024MB)
DOWNLOAD_MAXSIZE = 1048576 # 1Mb.

# Default: 33554432 (32MB)
DOWNLOAD_WARNSIZE = 524288 # 0.5Mb

# If the spider remains open for more than that number of seconds, it will be automatically closed with the reason closespider_timeout
CLOSESPIDER_TIMEOUT = 1800 # i.e. 30 minutes

# Disable cookies (enabled by default)
#COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
#DEFAULT_REQUEST_HEADERS = {
#   'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
#   'Accept-Language': 'en',
#}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    'indexer.middlewares.IndexerSpiderMiddleware': 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#DOWNLOADER_MIDDLEWARES = {
#    'indexer.middlewares.IndexerDownloaderMiddleware': 543,
#}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    'scrapy.extensions.telnet.TelnetConsole': None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
#ITEM_PIPELINES = {
#    'indexer.pipelines.IndexerPipeline': 300,
#}

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
#AUTOTHROTTLE_ENABLED = True
# The initial download delay
#AUTOTHROTTLE_START_DELAY = 5
# The maximum download delay to be set in case of high latencies
#AUTOTHROTTLE_MAX_DELAY = 60
# The average number of requests Scrapy should be sending in parallel to
# each remote server
#AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Enable showing throttling stats for every response received:
#AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = 'httpcache'
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = 'scrapy.extensions.httpcache.FilesystemCacheStorage'
