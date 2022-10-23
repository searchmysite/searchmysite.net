from flask import url_for, current_app
from urllib.request import urlopen, Request
import json
import math
from datetime import datetime
import config
import searchmysite.solr


# Utils to get params and data required to perform search
# -------------------------------------------------------

# Get all the search params, irrespective of whether a GET or a POST, setting sensible defaults
# Current list is: q, p, sort
# plus the facets in the possible_facets list below which are returned in the filter_query dict
def get_search_params(request):
    # Set defaults
    # If running flask locally for dev request.path will be e.g. /search/new/ and there won't be a request.root_path
    # but if running flask in the Apache container request.path will be e.g. /new/ and request.root_path will be /search
    if hasattr(request, 'root_path'):
        root_path = request.root_path
    else:
        root_path = ""
    path = root_path + request.path
    #current_app.logger.debug('path: {}'.format(path))
    if path == url_for('search.search'):
        sort = searchmysite.solr.default_sort_search
    elif path == url_for('search.browse'):
        sort = searchmysite.solr.default_sort_browse
    elif path == url_for('search.newest'):
        sort = searchmysite.solr.default_sort_newest
    else:
        sort = searchmysite.solr.default_sort_search
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
    #current_app.logger.debug('get_search_params: {}'.format(search_params))
    return search_params

# Get start parameter for Solr query
def get_start(current_page, results_per_page):
    start = (current_page * results_per_page) - results_per_page # p1 is start 0, p2 is start 10, p3 is start 20 etc. if results_per_page = 10
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
# If groupbydomain there will be a different number of results for pagination and display
# given the total number of results (for display) is likely to contain domains with more than one result
# but for pagination you need the number of domains with results. 
def get_no_of_results(search_results, groupbydomain):
    if groupbydomain:
        no_of_results_for_pagination = search_results['grouped']['domain']['ngroups'] 
        no_of_results_for_display = search_results['grouped']['domain']['matches']
    else:
        no_of_results_for_pagination = search_results['response']['numFound']
        no_of_results_for_display = no_of_results_for_pagination
    #current_app.logger.debug('no_of_results_for_pagination: {}, no_of_results_for_display: {}'.format(no_of_results_for_pagination, no_of_results_for_display))
    return (no_of_results_for_pagination, no_of_results_for_display)

# Return the range of pages that will be shown on the results
def get_page_range(current_page, no_of_results, results_per_page, max_pages_to_display):
    last_results_page = int(math.ceil(no_of_results / results_per_page)) # round up to nearest int, so e.g. 11 results is 2 pages rather than 1
    # the following is from https://codereview.stackexchange.com/questions/92137/creating-a-page-number-array-for-pagination?rq=1
    range_start = max(min(current_page - (max_pages_to_display - 1) // 2, last_results_page - max_pages_to_display + 1), 1)
    range_end = min(max(current_page + max_pages_to_display // 2, max_pages_to_display), last_results_page) + 1
    return range(range_start, range_end)

# Get a link to the query, with filters and sort applied if necessary.
# The filter queries are separate parameters, as they would be if selected via the Filters.
# This isn't standarad Solr query syntax, where they would be in the q or fq, but they will be translated to fq.
# Excludes pagination.
def get_link(query, filter_queries, sort, default_sort):
    link = 'q=' + query
    for filter_query in filter_queries:
        filter_values = filter_queries[filter_query]
        for filter_value in filter_values:
            link = link + '&' + filter_query + '=' + filter_value
    if sort != default_sort:
        link = link + '&sort=' + sort
    return link

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
                facet['label_name'] = "Owner verified"
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
# The groupbydomain section is only used by the main search (but not when the query restricts to one domain), so
# Browse and Newest (and the main search when query doesn't restrict to one domain) use the else section.
# See the fl in the query params to see which fields are available on which search, 
# e.g. date_domain_added, tags, web_feed etc. are only used on the Browse display.
def get_display_results(search_results, groupbydomain, params, link):
    results = []
    if groupbydomain:
        for domain_results in search_results['grouped']['domain']['groups']:
            # The first result per domain should be represented in exactly the same format as if not groupbydomain
            first_result_from_domain = domain_results['doclist']['docs'][0]
            result = {}
            result['url'] = first_result_from_domain['url']
            (full_title, short_title) = get_title(first_result_from_domain.get('title'), first_result_from_domain['url']) # title could be None, url is always set
            result['full_title'] = full_title
            result['short_title'] = short_title
            highlight = get_highlight(search_results['highlighting'], first_result_from_domain['url'], first_result_from_domain.get('description'))
            if highlight: result['highlight'] = highlight
            if 'published_date' in first_result_from_domain:
                published_date_string = first_result_from_domain['published_date']
                published_date_datetime = datetime.strptime(published_date_string, "%Y-%m-%dT%H:%M:%SZ") # e.g. 2020-07-18T06:11:22Z
                result['published_date'] = published_date_datetime.strftime('%d %b %Y')# add ", %H:%M%z" for time
            if 'contains_adverts' in first_result_from_domain: result['contains_adverts'] = first_result_from_domain['contains_adverts']
            # If there is more than one result for a domain, these will be respresented as a list of dicts, with some extra values for the display
            if len(domain_results['doclist']['docs']) > 1:
                subresults = []
                for doc in domain_results['doclist']['docs'][1:]: # Not getting the first item in the list because we have that already
                    subresult = {}
                    subresult['url'] = doc['url']
                    (subresult_full_title, subresult_short_title) = get_title(doc.get('title'), doc['url'])
                    subresult['full_title'] = subresult_full_title
                    subresult['short_title'] = subresult_short_title
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
            #current_app.logger.debug('search_results: {}'.format(search_results))
            result = {}
            result['url'] = search_result['url']
            (full_title, short_title) = get_title(search_result.get('title'), search_result['url']) # title could be None, url is always set
            result['full_title'] = full_title
            result['short_title'] = short_title
            if 'domain' in search_result: result['domain'] = search_result['domain']
            if 'date_domain_added' in search_result:
                domain_added_string = search_result['date_domain_added']
                domain_added_datetime = datetime.strptime(domain_added_string, "%Y-%m-%dT%H:%M:%SZ") # e.g. 2020-07-18T06:11:22Z
                result['date_domain_added'] = domain_added_datetime.strftime('%d %b %Y')# add ", %H:%M%z" for time
            if 'tags' in search_result:
                tags_list = search_result['tags']
                tags_truncation_point = 10 # Just so the display doesn't get taken over by a site that does keyword stuffing
                if len(tags_list) > tags_truncation_point:
                    result['tags'] = tags_list[:tags_truncation_point]
                    result['tags_truncated'] = True
                else:
                    result['tags'] = tags_list
                    result['tags_truncated'] = False
            if 'highlighting' in search_results:
                highlight = get_highlight(search_results['highlighting'], search_result['url'], search_result.get('description'))
                if highlight: result['highlight'] = highlight
            if 'web_feed' in search_result: result['web_feed'] = search_result['web_feed']
            if 'contains_adverts' in search_result: result['contains_adverts'] = search_result['contains_adverts']
            results.append(result)
    return results


# Utils used by get_display_results
# ---------------------------------

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

def get_highlight(highlighting, url, description):
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
    if highlight: highlight = highlight.split(searchmysite.solr.split_text) # Turn it into a list where highlight[1] is the highlighted term, so we wrap term in a <b> tag but HTML escape everything else 
    return highlight
