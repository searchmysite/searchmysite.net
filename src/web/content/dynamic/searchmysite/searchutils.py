from flask import url_for, current_app
from urllib.request import urlopen, Request
import json
import math
from datetime import datetime
import psycopg2.extras
import config
import searchmysite.solr
import searchmysite.sql
from searchmysite.db import get_db
from searchmysite.adminutils import get_host


# Utils to get params and data required to perform search
# -------------------------------------------------------

# Get all the search params, irrespective of whether a GET or a POST, setting sensible defaults (using search_type)
# Current list is: q, p, sort
# plus the facets in the possible_facets list below which are returned in the filter_query dict
def get_search_params(request, search_type):
    # Set defaults
    if search_type == 'search':
        sort = searchmysite.solr.default_sort_search
        default_results_per_page = searchmysite.solr.default_results_per_page_search
    elif search_type == 'browse':
        sort = searchmysite.solr.default_sort_browse
        default_results_per_page = searchmysite.solr.default_results_per_page_browse
    elif search_type == 'newest':
        sort = searchmysite.solr.default_sort_newest
        default_results_per_page = searchmysite.solr.default_results_per_page_newest
    else:
        sort = searchmysite.solr.default_sort_search
        default_results_per_page = searchmysite.solr.default_results_per_page_search
    search_params = {}
    # q, i.e. search query
    # Note that with edismax, for the links that just have fq, i.e. do not have q specified, we need to have q as * to get results.
    query = request.args.get('q', '*')
    if query == '': query = '*' # for cases when when there is a q but no value, i.e. ?q=
    search_params['q'] = query
    # page, i.e. current page, starting on 1
    if request.method == 'GET':
        current_page = request.args.get('page', 1)
    elif request.method == 'POST':
        current_page = request.form.get('page')
    try:
        current_page = int(current_page)
    except:
        current_page = 1
    search_params['page'] = current_page
    # sort, i.e. sort order
    # e.g. "score desc", "published_date desc", "date_domain_added desc", "domain desc", "indexed_inlink_domains_count desc"
    if request.method == 'GET':
        if request.args.get('sort') :
            sort = request.args.get('sort') 
    elif request.method == 'POST':
        if request.form.get('sort'):
            sort = request.form.get('sort')
    search_params['sort'] = sort
    # filter_queries, i.e. the facets selected to filter the query
    # This will be a dict with the facet name for the key and a list for the value
    # It will only contain facet names from those defined in the query facets variables 
    possible_facets = list(set(list(searchmysite.solr.query_facets_search.keys()) + list(searchmysite.solr.query_facets_browse.keys()) + list(searchmysite.solr.query_facets_newest.keys())))
    filter_queries = {}
    if request.method == 'GET':
        keys = request.args.keys()
    elif request.method == 'POST':
        keys = request.form.keys()
    for key in keys:
        if key in possible_facets:
            values = []
            if request.method == 'GET':
                values = request.args.getlist(key)
            elif request.method == 'POST':
                values = request.form.getlist(key)
            if values != []:
                filter_queries[key] = values
    search_params['filter_queries'] = filter_queries
    # resultsperpage
    resultsperpage = request.args.get('resultsperpage', default_results_per_page)
    try:
        resultsperpage = int(resultsperpage)
    except:
        resultsperpage = default_results_per_page
    search_params['resultsperpage'] = resultsperpage
    #current_app.logger.debug('get_search_params: {}'.format(search_params))
    return search_params

# Get start parameter for Solr query
def get_start(params):
    start = (params['page'] * params['resultsperpage']) - params['resultsperpage'] # p1 is start 0, p2 is start 10, p3 is start 20 etc. if results_per_page = 10
    return start

# Construct the fq (filter query) list, used to generate the fq string for Solr from the facets in the filters list.
# The list will be of the form ['name1:"value"', 'name2:("value1" AND "value2")']
# The double quotes are required so that values with spaces and special characters such as : work.
# The multi-values separated by AND are only currently an option with tags, because the schema is multiValued="true".
# In other cases the filters are mutually exclusive, e.g. selecting owner_verified = True will return 
# a result set where there are no owner_verified = False, or selecting site_category = "personal-website"
# will return a result set with no site_category = "independent-website"
def get_filter_queries(filter_queries):
    fq = []
    for filter in filter_queries:
        filter_values = filter_queries[filter]
        if len(filter_values) == 1:
            filter_query = filter + ":\"" + filter_values[0] + "\""
        else:
            filter_query = filter + ":("
            for i, filter_value in enumerate(filter_values): # i will be a number starting 0
                if i: # first item in the list will be i=0 so don't prepend with " AND "
                    filter_query = filter_query + " AND "
                filter_query = filter_query + "\"" + filter_value + "\""
            filter_query = filter_query + ")"
        fq.append(filter_query)
    #current_app.logger.debug('get_filter_queries: {}'.format(fq))
    return fq


# Perform the actual search
# -------------------------

# Construct the search query params and facets
# q and group are only required for the main search
# start, sort and fq are required for all
def do_search(query_params, query_facets, params, start, default_filter_queries, filter_queries, groupbydomain):
    solrquery = config.SOLR_URL + searchmysite.solr.solr_request_handler
    query_params['q'] = params['q']
    query_params['start'] = start
    query_params['sort'] = params['sort']
    query_params['fq'] = default_filter_queries + filter_queries
    query_params['group'] = groupbydomain
    solr_search = {}
    solr_search['params'] = query_params
    solr_search['facet'] = query_facets
    solr_search_json = json.dumps(solr_search)
    # current_app.logger.debug('solr_search_json: {}'.format(solr_search_json))
    req = Request(solrquery, solr_search_json.encode("utf8"), searchmysite.solr.solr_request_headers)
    response = urlopen(req)
    search_results = json.load(response)
    return search_results


# Utils to get data required to display the results
# -------------------------------------------------

# Return the number of results
# If groupbydomain there is likely to be a different number of total results vs total domains.
# The latter is required in two cases:
# 1. On the normal search results page, in the normal (non groupbydomain) mode which shows additional 
#    sub-results for each domain, you want to show the total number of results at the top, but use the 
#    total domains (i.e. groups of results) for calculating the pagination.
# 2. On the Newest Pages, a groupbydomain query is used to ensure only one result per domain, so you
#    want to show the total number of domains at the top rather than the total number of results. 
def get_no_of_results(search_results, groupbydomain):
    if groupbydomain:
        total_results = search_results['grouped']['domain']['matches']
        total_domains = search_results['grouped']['domain']['ngroups'] 
    else:
        total_results = search_results['response']['numFound']
        total_domains = total_results # There isn't a separate value in this case so just use total_results
    return (total_results, total_domains)

# Return the range of pages that will be shown on the results
def get_page_range(current_page, no_of_results, results_per_page, max_pages_to_display):
    last_results_page = int(math.ceil(no_of_results / results_per_page)) # round up to nearest int, so e.g. 11 results is 2 pages rather than 1
    # the following is from https://codereview.stackexchange.com/questions/92137/creating-a-page-number-array-for-pagination?rq=1
    range_start = max(min(current_page - (max_pages_to_display - 1) // 2, last_results_page - max_pages_to_display + 1), 1)
    range_end = min(max(current_page + max_pages_to_display // 2, max_pages_to_display), last_results_page) + 1
    return range(range_start, range_end)

# Get link to the query, with filters and sort applied if necessary.
# The filter queries are separate parameters, as they would be if selected via the Filters - note that 
# this isn't standard Solr query syntax, where they would be in the q or fq, but they will be translated to fq.
# query_string is the string after the ?, and excludes pagination. It is used to generate subresults_link where subresults are present.
# full_link is the full link to a results page, including pagination
# full_feed_link is the full link to the feed, also including pagination
# opensearchdescription is a full link to /opensearch.xml
def get_links(request, params, search_type):
    query = params['q']
    filter_queries = params['filter_queries']
    sort = params['sort']
    if search_type == 'search':
        default_sort = searchmysite.solr.default_sort_search
        full_link_url_for = url_for('search.search')
        full_feed_link_url_for = url_for('searchapi.feed_search', format='feed')
        query_string = 'q=' + query
    elif search_type == 'browse':
        default_sort = searchmysite.solr.default_sort_browse
        full_link_url_for = url_for('search.browse')
        full_feed_link_url_for = url_for('searchapi.feed_browse', format='feed')
        query_string = '' # /search/browse/ and /search/new/ don't have query strings
    elif search_type == 'newest':
        default_sort = searchmysite.solr.default_sort_newest
        full_link_url_for = url_for('search.newest')
        full_feed_link_url_for = url_for('searchapi.feed_newest', format='feed')
        query_string = '' # /search/browse/ and /search/new/ don't have query strings
    else:
        default_sort = searchmysite.solr.default_sort_search
        full_link_url_for = url_for('search.search')
        full_feed_link_url_for = url_for('searchapi.feed_search', format='feed')
        query_string = 'q=' + query
    if full_feed_link_url_for.startswith('/search/v1/'): full_feed_link_url_for = full_feed_link_url_for.replace('/search/v1/', '/api/v1/', 1) # This shouldn't be necessary, and there should be a better solution
    if params['page'] != 1: # Default is 1, so only show page link if not the default
        page = '&page=' + str(params['page'])
    else:
        page = ''
    links = {}
    host_url = get_host(request.host_url, request.headers)
    if host_url.endswith('/'): host_url = host_url[:-1] 
    #current_app.logger.debug('host_url: {}, full_link_url_for: {}, full_feed_link_url_for: {}'.format(host_url, full_link_url_for, full_feed_link_url_for))
    # query_string
    for filter_query in filter_queries:
        filter_values = filter_queries[filter_query]
        for filter_value in filter_values:
            if query_string == '':
                query_string = query_string + filter_query + '=' + filter_value
            else:
                query_string = query_string + '&' + filter_query + '=' + filter_value
    if sort != default_sort:
        query_string = query_string + '&sort=' + sort
    links['query_string'] = query_string
    # full_link
    if query_string == '' and page == '':
        full_link = host_url + full_link_url_for
    else:
        full_link = host_url + full_link_url_for + '?' + query_string + page
    links['full_link'] = full_link
    # full_feed_link
    if query_string == '' and page == '':
        full_feed_link = host_url + full_feed_link_url_for
    else:
        full_feed_link = host_url + full_feed_link_url_for + '?' + query_string + page
    links['full_feed_link'] = full_feed_link
    # opensearchdescription
    links['opensearchdescription'] = host_url + '/opensearch.xml'
    #current_app.logger.debug('query_string: {}, full_link: {}, full_feed_link: {}, opensearchdescription: {}'.format(query_string, full_link, full_feed_link, links['opensearchdescription'] ))
    return links

# Construct the pagination data for rendering on the page.
# Output is of the format:
# {"1": None, "2": "2", "3": "3"}
# i.e. label and value for the link (None if no link)
def get_display_pagination(current_page, pages):
    pagination = {}
    for page in pages:
        if page == current_page:
            pagination[page] = None
        else:
            pagination[page] = page
    return pagination

# Construct the facets for rendering on the page.
# Input is of the format:
# "facets":{
#   "count":23,
#   "<facet1>":{ "buckets":[{ "val":"<name>", "count":<value>} ... ]}
#   "<facet2>":{ "buckets":[{ "val":"<name>", "count":<value>} ... ]}
#   ...
# }
# Output is of the format:
# [ 
# {'label_name': '<facet1-label>', 'inputs': [{'type': 'checkbox', 'name': '<facet1>', 'value': '<facet1-value1>', 'state': '', 'id': '<facet1>-<facet1-value1>', 'label': '<facet1-label1>'}, {'type': 'checkbox', 'name': '<facet1>', 'value': '<facet1-value2>' ...} ... ]}, 
# {'label_name': '<facet2-label>', 'inputs': [{...}]} 
# ]
def get_display_facets(filter_queries, results):
    facets = []
    for facet_field in results['facets']:
        if facet_field != "count":
            facet = {}
            if facet_field == "site_category":
                facet['label_name'] = "Category"
            elif facet_field == "tags":
                facet['label_name'] = "Tags"
            elif facet_field == "owner_verified":
                facet['label_name'] = "Full listing"
            elif facet_field == "contains_adverts":
                facet['label_name'] = "Contains adverts"
            elif facet_field == "indexed_inlink_domains_count":
                facet['label_name'] = "Inlink domains"
            elif facet_field == "in_web_feed":
                facet['label_name'] = "In web feed"
            elif facet_field == "language_primary":
                facet['label_name'] = "Language"
            else:
                facet['label_name'] = facet_field
            inputs = []
            facet_values = results['facets'][facet_field]['buckets']
            for facet_value in facet_values:
                #current_app.logger.debug('facet_field: {}, facet_value: {}'.format(facet_field, facet_value['val']))
                value = facet_value['val']
                count = facet_value['count']
                input = {}
                input['type'] = "checkbox"
                input['name'] = facet_field
                input['value'] = value
                if filter_queries.get(facet_field) and str(value) in filter_queries.get(facet_field):
                    input['state'] = "checked"
                else:
                    input['state'] = ""
                input['id'] = facet_field + "-" + str(value)
                input['label'] = str(value) + " (" + str(count) + ")"
                inputs.append(input)
            facet['inputs'] = inputs
            facets.append(facet)
    return facets

# Construct the results
# Output is a list of dicts.
# If groupbydomain, the result dict will have a subresults list of dicts.
# The groupbydomain section is only used by the main search (but not when the query restricts to one domain), 
# and Newest (to ensure only one post per domain), so Browse and Newest (and the main search when query 
# doesn't restrict to one domain) use the else section.
def get_display_results(search_results, groupbydomain, params, link):
    results = []
    if groupbydomain:
        for domain_results in search_results['grouped']['domain']['groups']:
            first_result_from_domain = domain_results['doclist']['docs'][0]
            result = extract_data_from_result(first_result_from_domain, search_results, False)
            # If there is more than one result for a domain, these will be respresented as a list of dicts, with some extra values for the display
            if len(domain_results['doclist']['docs']) > 1:
                subresults = []
                for doc in domain_results['doclist']['docs'][1:]: # Not getting the first item in the list because we have that already
                    subresult = extract_data_from_result(first_result_from_domain, search_results, True)
                    subresults.append(subresult)
                result['subresults'] = subresults
                subresults_domain  = domain_results['groupValue']
                subresults_total = int(domain_results['doclist']['numFound'])
                link_minus_query = link.replace('q='+params['q'], '')
                result['subresults_link'] = 'q=' + params['q'] + '%20%2Bdomain:' + subresults_domain + link_minus_query # The + (%2B) before domain ensures that term is mandatory, otherwise multi word queries would treat the domain as optional
                result['subresults_link_text'] = "All " + str(subresults_total) + " results from " + subresults_domain
            results.append(result)
    else:
        for search_result in search_results['response']['docs']:
            result = extract_data_from_result(search_result, search_results, False)
            results.append(result)
    #current_app.logger.debug('results: {}'.format(results))
    return results


# Utils used by API
# -----------------

# Checks if the API is enabled or not for a domain
# Returns True or False, or None is the domain isn't found
# Requires a database lookup for every API request, which isn't ideal
def check_if_api_enabled_for_domain(domain):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(searchmysite.sql.sql_check_api_enabled, (domain,))
    result = cursor.fetchone()
    if not result:
        api_enabled_for_domain = None
    elif result['api_enabled'] == True:
        api_enabled_for_domain = True
    elif result['api_enabled'] == False:
        api_enabled_for_domain = False
    else:
        api_enabled_for_domain = None
    return api_enabled_for_domain


# Utils used by other utils
# -------------------------

# Used by get_params 
# Figure out if the request is of type api or search, and subtype search, browse or newest (which e.g. have different defaults for sort)
#def get_type_and_subtype(request):
#    type = 'search' # 'search' = /search*, 'api' = /api*
#    subtype = 'search' # 'search' = */search/, 'browse' = */search/browse/, 'newest' = */search/newest/
#    # If running flask locally for dev request.path will be e.g. /search/new/ and there won't be a request.root_path
#    # but if running flask in the Apache container request.path will be e.g. /new/ and request.root_path will be /search
#    if hasattr(request, 'root_path'):
#        root_path = request.root_path
#    else:
#        root_path = ""
#    path = root_path + request.path
#    if path == url_for('search.search') or path == url_for('search.browse') or path == url_for('search.newest'):
#        type = 'search'
#    elif path == url_for('api.feed', format='feed'):
#        type = 'api'
#    if path == url_for('search.search') or path == url_for('api.feed', format='feed'):
#        subtype = 'search'
#    elif path == url_for('search.browse'):
#        subtype = 'browse'
#    elif path == url_for('search.newest'):
#        subtype = 'newest'
#    #current_app.logger.debug('path: {}, type: {}, subtype: {}'.format(path, type, subtype))
#    return (type, subtype)

# Used by get_display_results
# To extract the fields from the results, and format for display if necessary.
# Not all queries will return all fields, e.g. domain, date_domain_added, tags and web_feed 
# are just used by Browse.
# See the fl in the query params to see which fields are available on which search.
# All results including subresults will have id, url and some form of title, but other fields are only set 
# for non-subresults.
def extract_data_from_result(result, results, subresult):
    data = {}
    data['id'] = result['id']
    data['url'] = result['url']
    (full_title, short_title) = get_title(result.get('title'), result['url']) # title could be None, url is always set
    data['full_title'] = full_title
    data['short_title'] = short_title
    if subresult == False:
        if 'highlighting' in results:
            highlight = get_highlight(results['highlighting'], result['url'], result.get('description'))
            if highlight: data['highlight'] = highlight
        if 'published_date' in result:
            published_date_string = result['published_date']
            published_date_datetime = datetime.strptime(published_date_string, "%Y-%m-%dT%H:%M:%SZ") # e.g. 2020-07-18T06:11:22Z
            data['published_date'] = published_date_datetime.strftime('%d %b %Y')# add ", %H:%M%z" for time
            data['published_datetime'] = published_date_string
        if 'contains_adverts' in result: data['contains_adverts'] = result['contains_adverts']
        if 'domain' in result: data['domain'] = result['domain']
        if 'date_domain_added' in result:
            domain_added_string = result['date_domain_added']
            domain_added_datetime = datetime.strptime(domain_added_string, "%Y-%m-%dT%H:%M:%SZ") # e.g. 2020-07-18T06:11:22Z
            data['date_domain_added'] = domain_added_datetime.strftime('%d %b %Y')# add ", %H:%M%z" for time
        if 'tags' in result:
            tags_list = result['tags']
            tags_truncation_point = 10 # Just so the display doesn't get taken over by a site that does keyword stuffing
            if len(tags_list) > tags_truncation_point:
                data['tags'] = tags_list[:tags_truncation_point]
                data['tags_truncated'] = True
            else:
                data['tags'] = tags_list
                data['tags_truncated'] = False
        if 'web_feed' in result: data['web_feed'] = result['web_feed']
    return data

# Used by get_display_results
# To get the full title, and if it is long a shorter title 
def get_title(title, url):
    if title:
        full_title = title
    else:
        full_title = url
    if len(full_title) > 100:
        short_title = full_title[0:100] + "..."
    else:
        short_title = full_title
    return (full_title, short_title)

# Used by get_display_results
# To get the highlighted text, returned as a list where the highlighted terms is highlight[1], highlight[3]
# Which makes it easier to highlight without knowing if it needs to be HTML escaped
def get_highlight(highlighting, url, description):
    #current_app.logger.debug('highlighting: {}, url: {}, description: {}'.format(highlighting, url, description))
    highlight = None
    if 'content' in highlighting[url]:
        highlight = "... " + highlighting[url]['content'][0] + " ..."
    elif 'description' in highlighting[url]:
        highlight = "... " + highlighting[url]['description'][0] + " ..."
    elif description:
        if len(description) > 500:
            highlight = description[0:500] + '...'
        else:
            highlight = description
    if highlight: highlight = highlight.split(searchmysite.solr.split_text)
    #current_app.logger.debug('highlight: {}'.format(highlight))
    return highlight
