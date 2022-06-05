import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.exceptions import DropItem
from bs4 import BeautifulSoup, SoupStrainer
import datetime
from scrapy.utils.log import configure_logging
from scrapy.utils.project import get_project_settings
import logging
from common.utils import extract_domain_from_url, convert_string_to_utc_date, convert_datetime_to_utc_date, get_text

# Solr schema is:
#    <field name="url" type="string" indexed="true" stored="true" required="true" />
#    <field name="domain" type="string" indexed="true" stored="true" required="true" />
#    <field name="is_home" type="boolean" indexed="true" stored="true" /> <!-- true for home page, false for all other pages -->
#    <field name="title" type="text_general" indexed="true" stored="true" multiValued="false" />
#    <field name="author" type="string" indexed="true" stored="true" />
#    <field name="description" type="text_general" indexed="true" stored="true" multiValued="false" />
#    <field name="tags" type="string" indexed="true" stored="true" multiValued="true" />
#    <field name="body" type="text_general" indexed="true" stored="true" multiValued="false" />
#    <field name="content" type="text_general" indexed="true" stored="true" multiValued="false" />
#    <field name="page_type" type="string" indexed="true" stored="true" />
#    <field name="page_last_modified" type="pdate" indexed="true" stored="true" />
#    <field name="published_date" type="pdate" indexed="true" stored="true" />
#    <field name="indexed_date" type="pdate" indexed="true" stored="true" />
#    <field name="date_domain_added" type="pdate" indexed="true" stored="true" /> <!-- only present on pages where is_home=true -->
#    <field name="site_category" type="string" indexed="true" stored="true" />
#    <field name="site_last_modified" type="pdate" indexed="true" stored="true" /> <!-- same value for every page in a site -->
#    <field name="owner_verified" type="boolean" indexed="true" stored="true" /> <!-- same value for every page in a site -->
#    <field name="contains_adverts" type="boolean" indexed="true" stored="true" />
#    <field name="api_enabled" type="boolean" indexed="true" stored="true" /> <!-- only present on pages where is_home=true -->
#    <field name="public" type="boolean" indexed="true" stored="true" /> <!-- include in public search (false only an option where owner_verified=true) -->
#    <field name="language" type="string" indexed="true" stored="true" />
#    <field name="language_primary" type="string" indexed="true" stored="true" />
#    <field name="indexed_inlinks" type="string" indexed="true" stored="true" multiValued="true" />
#    <field name="indexed_inlinks_count" type="pint" indexed="true" stored="true" />
#    <field name="indexed_inlink_domains" type="string" indexed="true" stored="true" multiValued="true" />
#    <field name="indexed_inlink_domains_count" type="pint" indexed="true" stored="true" />
#    <field name="indexed_outlinks" type="string" indexed="true" stored="true" multiValued="true" />

def customparser(response, domain, is_home, domains_for_indexed_links, site_config, common_config):
    configure_logging(get_project_settings())
    logger = logging.getLogger()
    logger.info('Parsing {}'.format(response.url))

    # check for type (this is first because some types might be on the exclude type list and we want to return None so it isn't yielded)
    ctype = response.xpath('//meta[@property="og:type"]/@content').get() # <meta property="og:type" content="..." />
    if not ctype: ctype = response.xpath('//article/@data-post-type').get() # <article data-post-id="XXX" data-post-type="...">
    exclusions = site_config['exclusions']
    if exclusions:
        for exclusion in exclusions:
            if exclusion['exclusion_type'] == 'type':
                if exclusion['exclusion_value'] == ctype:
                    logger.info('Excluding item because type "{}" is on type exclusion list'.format(ctype))
                    return None

    item = {}
    item['page_type'] = ctype

    # id
    item['id'] = response.url

    # url
    item['url'] = response.url

    # domain
    item['domain'] = domain

    # is_home, i.e. the page is the home page
    if is_home:
        logger.info('Setting home page: {}'.format(response.url))
    item['is_home'] = is_home

    # title
    item['title'] = response.xpath('//title/text()').get() # <title>...</title>

    # author
    item['author'] = response.xpath('//meta[@name="author"]/@content').get() # <meta name="author" content="...">

    # description
    description = response.xpath('//meta[@name="description"]/@content').get() # <meta name="description" content="...">
    if not description: description = response.xpath('//meta[@property="og:description"]/@content').get() # <meta property="og:description" content="..." />
    item['description'] = description

    # tags
    # Should be comma delimited as per https://www.w3.org/TR/2011/WD-html5-author-20110809/the-meta-element.html
    # but unfortunately some sites are space delimited
    tags = response.xpath('//meta[@name="keywords"]/@content').get() # <meta name="keywords" content="...">
    if not tags: tags = response.xpath('//meta[@property="article:tag"]/@content').get() # <meta property="article:tag" content="..."/>
    tag_list = []
    if tags:
        if tags.count(',') == 0 and tags.count(' ') > 1: # no commas and more than one space
            for tag in tags.split(" "):
                tag_list.append(tag.lstrip())
        else:
            for tag in tags.split(","):
                tag_list.append(tag.lstrip())
    item['tags'] = tag_list

    # body
    only_body = SoupStrainer('body')
    body_html = BeautifulSoup(response.text, 'lxml', parse_only=only_body)
    #for script in body_html(["script", "style"]): # Remove script and style tags and their contents
    #    script.decompose()
    #body_text = get_text(body_html)
    #item['body'] = body_text

    # content
    for non_content in body_html(["nav", "header", "footer"]): # Remove nav, header, and footer tags and their contents
        non_content.decompose()
    main_html = body_html.find('main')
    article_html = body_html.find('article')
    if main_html:
        content_text = get_text(main_html)
    elif article_html:
        content_text = get_text(article_html)
    else:
        content_text = get_text(body_html)
    item['content'] = content_text

    # last_modified_date
    last_modified_date = response.headers.get('Last-Modified')
    if last_modified_date:
        last_modified_date = last_modified_date.decode('utf-8')
        last_modified_date = convert_string_to_utc_date(last_modified_date)
    item['page_last_modified'] = last_modified_date

    # published_date
    published_date = response.xpath('//meta[@property="article:published_time"]/@content').get()
    if not published_date: published_date = response.xpath('//meta[@name="dc.date.issued"]/@content').get()
    if not published_date: published_date = response.xpath('//meta[@itemprop="datePublished"]/@content').get()
    published_date = convert_string_to_utc_date(published_date)
    item['published_date'] = published_date

    # indexed_date
    indexed_date = convert_datetime_to_utc_date(datetime.datetime.now())
    item['indexed_date'] = indexed_date

    # date_domain_added - only set if the entry is the home page
    date_domain_added = None
    if is_home == True:
        date_domain_added = site_config['date_domain_added']
        date_domain_added = convert_datetime_to_utc_date(date_domain_added)
    item['date_domain_added'] = date_domain_added

    # site_category
    item['site_category'] = site_config['site_category']

    # owner_verified
    # Only set owner_verified within the search index when api_enabled
    # This is because there are a growing number of Verified Add sites which have indexing_enabled (either via Quick Add or expired Verified Add)
    # and complete step 3 of the Verified Add process, i.e. verify ownership, which sets owner_verified, 
    # but don't complete step 4, i.e. payment (when present), which sets api_enabled, indexing_frequency etc.
    owner_verified = False
    if site_config['owner_verified'] == True and site_config['api_enabled'] == True: 
        owner_verified = True
    item['owner_verified'] = owner_verified

    # contains_adverts
    # Just looks for Google Ads at the moment
    contains_adverts = False # assume a page has no adverts unless proven otherwise
    if response.xpath('//ins[contains(@class,"adsbygoogle")]') != []: contains_adverts = True
    item['contains_adverts'] = contains_adverts

    # api_enabled - only set if the entry is the home page
    api_enabled = None
    if is_home == True:
        api_enabled = site_config['api_enabled']
    item['api_enabled'] = api_enabled

    # public - should always be true, except in rare cases where owner_verified=true (but not checking to enforce)
    include_in_public_search = True
    if site_config['include_in_public_search'] == False:
        include_in_public_search = False
    item['public'] = include_in_public_search

    # language, e.g. en-GB
    language = response.xpath('/html/@lang').get()
    #if language: language = language.lower() # Lowercasing to prevent facetted nav thinking e.g. en-GB and en-gb are different
    item['language'] = language

    # language_primary, e.g. en
    language_primary = None
    if language:
        language_primary = language[:2] # First two characters, e.g. en-GB becomes en
    item['language_primary'] = language_primary

    # indexed_inlinks
    # i.e. the pages in the search collection on other domains which link to this page
    indexed_inlinks = []
    #logger.info('Processing indexed_inlinks for {}'.format(response.url))
    if response.url in site_config['indexed_inlinks']:
        #logger.info('Found an indexed_inlink: {}'.format(other_config['indexed_inlinks'][response.url]))
        indexed_inlinks = site_config['indexed_inlinks'][response.url]
    item['indexed_inlinks'] = indexed_inlinks

    # indexed_inlinks_count
    if len(indexed_inlinks) > 0:
        item['indexed_inlinks_count'] = len(indexed_inlinks)
    else:
        item['indexed_inlinks_count'] = None

    # indexed_inlink_domains
    indexed_inlink_domains = []
    if indexed_inlinks:
        for indexed_inlink in indexed_inlinks:
            indexed_inlink_domain = extract_domain_from_url(indexed_inlink, common_config['domains_allowing_subdomains'])
            if indexed_inlink_domain not in indexed_inlink_domains:
                indexed_inlink_domains.append(indexed_inlink_domain)
    item['indexed_inlink_domains'] = indexed_inlink_domains

    # indexed_inlink_domains_count
    if len(indexed_inlink_domains) > 0:
        item['indexed_inlink_domains_count'] = len(indexed_inlink_domains)
    else:
        item['indexed_inlink_domains_count'] = None

    # indexed_outlinks
    # i.e. the links in this page to pages in the search collection on other domains
    indexed_outlinks = []
    if domains_for_indexed_links:
        extractor = LinkExtractor(allow_domains=domains_for_indexed_links) # i.e. external links
        links = extractor.extract_links(response)
        for link in links:
            indexed_outlinks.append(link.url)
    item['indexed_outlinks'] = indexed_outlinks

    return item
