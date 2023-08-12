import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.exceptions import DropItem
from scrapy.http import HtmlResponse, XmlResponse
from bs4 import BeautifulSoup, SoupStrainer
import datetime
from scrapy.utils.log import configure_logging
from scrapy.utils.project import get_project_settings
import logging
import feedparser
from common.utils import extract_domain_from_url, convert_string_to_utc_date, convert_datetime_to_utc_date, get_text, get_content_chunks, get_vector

# Solr schema is:
#    <field name="url" type="string" indexed="true" stored="true" required="true" />
#    <field name="domain" type="string" indexed="true" stored="true" required="true" />
#    <field name="relationship" type="string" indexed="true" stored="true" /> <!-- relationship:parent for whole docs and relationship:child for part doc (i.e. chunks) -->
#    <field name="is_home" type="boolean" indexed="true" stored="true" /> <!-- true for home page, false for all other pages -->
#    <field name="title" type="text_general" indexed="true" stored="true" multiValued="false" />
#    <field name="author" type="string" indexed="true" stored="true" />
#    <field name="description" type="text_general" indexed="true" stored="true" multiValued="false" />
#    <field name="tags" type="string" indexed="true" stored="true" multiValued="true" />
#    <field name="content" type="text_general" indexed="true" stored="true" multiValued="false" />
#    <field name="content_last_modified" type="pdate" indexed="true" stored="true" multiValued="false" />
#    <field name="content_type" type="string" indexed="true" stored="true" />
#    <field name="page_type" type="string" indexed="true" stored="true" />
#    <field name="page_last_modified" type="pdate" indexed="true" stored="true" />
#    <field name="published_date" type="pdate" indexed="true" stored="true" />
#    <field name="indexed_date" type="pdate" indexed="true" stored="true" />
#    <field name="date_domain_added" type="pdate" indexed="true" stored="true" /> <!-- only present on pages where is_home=true -->
#    <field name="site_category" type="string" indexed="true" stored="true" /> <!-- same value for every page in a site -->
#    <field name="site_last_modified" type="pdate" indexed="true" stored="true" /> <!-- not currently in use -->
#    <field name="owner_verified" type="boolean" indexed="true" stored="true" /> <!-- same value for every page in a site -->
#    <field name="contains_adverts" type="boolean" indexed="true" stored="true" />
#    <field name="api_enabled" type="boolean" indexed="true" stored="true" /> <!-- only present on pages where is_home=true -->
#    <field name="public" type="boolean" indexed="true" stored="true" /> <!-- same value for every page (false only an option where owner_verified=true) -->
#    <field name="in_web_feed" type="boolean" indexed="true" stored="true" />
#    <field name="web_feed" type="string" indexed="true" stored="true" />
#    <field name="language" type="string" indexed="true" stored="true" />
#    <field name="language_primary" type="string" indexed="true" stored="true" />
#    <field name="indexed_inlinks" type="string" indexed="true" stored="true" multiValued="true" />
#    <field name="indexed_inlinks_count" type="pint" indexed="true" stored="true" />
#    <field name="indexed_inlink_domains" type="string" indexed="true" stored="true" multiValued="true" />
#    <field name="indexed_inlink_domains_count" type="pint" indexed="true" stored="true" />
#    <field name="indexed_outlinks" type="string" indexed="true" stored="true" multiValued="true" />
#    <fieldType name="knn_vector384" class="solr.DenseVectorField" vectorDimension="384" similarityFunction="dot_product"/>
#    <field name="content_chunk_no" type="pint" indexed="true" stored="true" /> <!-- only in relationship:child below content_chunks pseudo-field -->
#    <field name="content_chunk_text" type="string" indexed="true" stored="true" /> <!-- only in relationship:child below content_chunks pseudo-field -->
#    <field name="content_chunk_vector" type="knn_vector384" indexed="true" stored="true"/> <!-- only in relationship:child below content_chunks pseudo-field -->

def customparser(response, domain, is_home, domains_for_indexed_links, site_config, common_config):

    configure_logging(get_project_settings())
    logger = logging.getLogger()
    logger.info('Parsing {}'.format(response.url))

    # check for type (this is first because some types might be on the exclude type list and we want to return None so it isn't yielded)
    ctype = None
    if isinstance(response, XmlResponse) or isinstance(response, HtmlResponse): # i.e. not a TextResponse like application/json which wouldn't be parseable via xpath
        # If the page returns a Content-Type suggesting XmlResponse or HtmlResponse but is e.g. JSON it will throw a "ValueError: Cannot use xpath on a Selector of type 'json'"
        try:
            ctype = response.xpath('//meta[@property="og:type"]/@content').get() # <meta property="og:type" content="..." />
            if not ctype: ctype = response.xpath('//article/@data-post-type').get() # <article data-post-id="XXX" data-post-type="...">
        except ValueError:
            logger.info('Aborting parsing for {}: not XmlResponse or HtmlResponse'.format(response.url))
            return None # Don't perform further parsing of this item in case it causes additional errors
    exclusions = site_config['exclusions']
    if exclusions and ctype:
        for exclusion in exclusions:
            if exclusion['exclusion_type'] == 'type':
                if exclusion['exclusion_value'] == ctype:
                    logger.info('Excluding item because type "{}" is on type exclusion list'.format(ctype))
                    return None

    item = {}


    # Attributes set on all TextResponse, including application/json
    # --------------------------------------------------------------

    original_url = response.url
    if 'redirect_urls' in response.request.meta:
        original_url = response.request.meta['redirect_urls'][0]
        logger.info('Redirect detected. Current URL: {}, original URL(s): {}, using {} for id'.format(response.url, response.request.meta['redirect_urls'], original_url))

    # id
    # This is the unique identifier for each page. If a second page is saved with the same id, it will overwrite the first page.
    # For that reason, if a redirect is detected, use the pre-redirect URL as the ID, to prevent overwriting. This is especially important for the home page,
    # to prevent a domain which redirects to another domain from overwriting the home page of that other domain.
    # This of course means that there will be cases where the id does not match the url field, but I don't think that will be an issue.
    item['id'] = original_url

    # url
    item['url'] = response.url

    # domain
    item['domain'] = domain

    # relationship
    item['relationship'] = 'parent' # only content_chunks is child

    # is_home, i.e. the page is the home page
    if is_home:
        logger.info('Setting home page: {}'.format(item['id']))
    item['is_home'] = is_home

    # content_type, e.g. text/html; charset=utf-8
    content_type = None
    content_type_header = response.headers.get('Content-Type')
    if content_type_header:
        content_type = content_type_header.decode('utf-8').split(';')[0]
    item['content_type'] = content_type

    # last_modified_date
    last_modified_date = response.headers.get('Last-Modified')
    if last_modified_date:
        last_modified_date = last_modified_date.decode('utf-8')
        last_modified_date = convert_string_to_utc_date(last_modified_date)
    item['page_last_modified'] = last_modified_date

    # indexed_date
    indexed_date = convert_datetime_to_utc_date(datetime.datetime.now())
    item['indexed_date'] = indexed_date

    # site_category
    item['site_category'] = site_config['site_category']

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

    # owner_verified
    # This used to be an explicit field, but now is set by search_my_site_scheduler.py when tier = 3
    owner_verified = False
    if site_config['owner_verified'] == True: 
        owner_verified = True
    item['owner_verified'] = owner_verified

    # api_enabled & date_domain_added
    # Now site in pipelines.py if is_home == True

    # public - should always be true, except in rare cases where owner_verified=true (but not checking to enforce)
    include_in_public_search = True
    if site_config['include_in_public_search'] == False:
        include_in_public_search = False
    item['public'] = include_in_public_search

    # web_feed - True if the page is in a web feed (RSS or Atom), False otherwise
    if response.url in site_config['feed_links']:
        item['in_web_feed'] = True
        item['web_feed'] = site_config['web_feed']
    else:
        item['in_web_feed'] = False


    # Attributes set only on XmlResponse and HtmlResponse, i.e. not TextResponse which includes application/json
    # ----------------------------------------------------------------------------------------------------------

    # i.e. not a TextResponse like application/json which wouldn't be parseable via xpath
    if isinstance(response, XmlResponse) or isinstance(response, HtmlResponse):

        # title
        # XML can have a title tag
        item['title'] = response.xpath('//title/text()').get() # <title>...</title>

        # indexed_outlinks
        # i.e. the links in this page to pages in the search collection on other domains
        indexed_outlinks = []
        if domains_for_indexed_links:
            extractor = LinkExtractor(allow_domains=domains_for_indexed_links) # i.e. external links
            links = extractor.extract_links(response)
            for link in links:
                indexed_outlinks.append(link.url)
        item['indexed_outlinks'] = indexed_outlinks


    # Attributes set only on HtmlResponse
    # -----------------------------------

    if isinstance(response, HtmlResponse):

        # page_type (value obtained at the start in case there was a page type exclusion) 
        item['page_type'] = ctype

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

        # content
        only_body = SoupStrainer('body')
        body_html = BeautifulSoup(response.text, 'lxml', parse_only=only_body)
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

        # content_last_modified
        # Get values already parsed from the current page
        new_content = content_text # from whole page, with nav, header etc. removed, and the remainder converted to plain text
        page_last_modified = last_modified_date # from Last-Modified HTTP header
        # Get values from the previously indexed version of this page
        previous_content = None
        previous_content_last_modified = None
        previous_contents = site_config['contents']
        if response.url in previous_contents: # If there was something at this URL last time (not necessarily with content and/or content_last_modified set)
            previous_page = previous_contents[response.url]
            if 'content' in previous_page:
                previous_content = previous_page['content']
            if 'content_last_modified' in previous_page:
                previous_content_last_modified = previous_page['content_last_modified']
        # Scenarios:
        # 1. Page content changed: use indexed_date
        # 2. Page content unchanged: use previous_content_last_modified or page_last_modified or indexed_date
        # 3. New page: use page_last_modified or indexed_date
        # 4. No page content (or something else): no value
        # Notes:
        # 1. page_last_modified is not necessarily when the content was last changed, but is more likely to nearer than indexed_date, 
        #    plus it saves a lot of content_last_modified values being set to the time this functionality is first run.
        # 2. If the logic to generate content_text changes in any way, even just in the way white space is treated,
        #    then that will trigger new values for content_last_modified, even if the actual content hasn't actually changed.
        if previous_content and new_content and previous_content != new_content:
            content_last_modified = indexed_date
            message = 'Updated page content: changing content_last_modified to {}'.format(content_last_modified)
        elif previous_content and new_content and previous_content == new_content:
            if previous_content_last_modified: # This will normally be set, but won't the first time this code is run against existing content
                content_last_modified = previous_content_last_modified
            elif page_last_modified:
                content_last_modified = page_last_modified
            else:
                content_last_modified = indexed_date
            message = 'Unchanged page content: using content_last_modified {}'.format(content_last_modified)
        elif new_content and not previous_content and not previous_content_last_modified:
            if page_last_modified:
                content_last_modified = page_last_modified
            else:
                content_last_modified = indexed_date
            message = 'New page: setting content_last_modified to {}'.format(content_last_modified)
        else:
            content_last_modified = None
            message = 'No page content: content_last_modified not being set'
        logger.debug(message)
        item['content_last_modified'] = content_last_modified

        # content_chunks (pseudo-field for nested documents)
        # Get values from the previously indexed version of this page
        previous_content_chunks = None
        if response.url in previous_contents: # previous_contents already defined above
            previous_page = previous_contents[response.url]
            if 'content_chunks' in previous_page:
                previous_content_chunks = previous_page['content_chunks']
        # Scenarios:
        # 1. Content has changed, or content is new, or there aren't any existing content_chunks (e.g. on first run) - regenerate
        # 2. Else reuse previous values
        # Note: A full reindex until now has always been a clean reindex, i.e. delete everything in the index for that domain and
        #    start afresh. However, with the content_chunks functionality, it is the first time content is potentially preserved
        #    between reindexes. So if the embedding config changes, the new config won't take effect for a page until it's content
        #    has changed. That may be fine for minor embedding config changes, e.g. a change to the chunk length, but could be breaking
        #    for significant embedding config changes, e.g. if the embedding model is changed. Suggestion in the case of significant
        #    config changes is to delete all embeddings, e.g. via <delete><query>relationship:child</query></delete> . 
        if (previous_content and new_content and previous_content != new_content) or (new_content and not previous_content) or (not previous_content_chunks):
            content_chunks = get_content_chunks(content_text, site_config['content_chunks_limit'], item['id'], item['url'], domain)
        else:
            logger.debug("Reusing existing embeddings for {}".format(item['id']))
            content_chunks = previous_content_chunks
        item['content_chunks'] = content_chunks

        # published_date
        published_date = response.xpath('//meta[@property="article:published_time"]/@content').get()
        if not published_date: published_date = response.xpath('//meta[@name="dc.date.issued"]/@content').get()
        if not published_date: published_date = response.xpath('//meta[@itemprop="datePublished"]/@content').get()
        published_date = convert_string_to_utc_date(published_date)
        item['published_date'] = published_date

        # contains_adverts
        # Just looks for Google Ads at the moment
        contains_adverts = False # assume a page has no adverts unless proven otherwise
        if response.xpath('//ins[contains(@class,"adsbygoogle")]') != []: contains_adverts = True
        item['contains_adverts'] = contains_adverts

        # language, e.g. en-GB
        language = response.xpath('/html/@lang').get()
        #if language: language = language.lower() # Lowercasing to prevent facetted nav thinking e.g. en-GB and en-gb are different
        item['language'] = language

        # language_primary, e.g. en
        language_primary = None
        if language:
            language_primary = language[:2] # First two characters, e.g. en-GB becomes en
        item['language_primary'] = language_primary

    elif isinstance(response, XmlResponse):

        # For XML this will record the rood node name 
        item['page_type'] = response.xpath('name(/*)').get()

        d = feedparser.parse(response.text)
        entries = d.entries
        version = None
        if entries:
            version = d.version
            item['is_web_feed'] = True


    return item
