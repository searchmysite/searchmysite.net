from flask import Flask, request, url_for, render_template, redirect, Blueprint, current_app
from urllib.request import urlopen, Request
from urllib.parse import quote, unquote
from os import environ
import json
import math
from random import randrange
from datetime import datetime, date
import config

bp = Blueprint('search', __name__)

# Variables
results_per_page_search = 10
results_per_page_browse = 20
results_per_page_newest = 12
max_pages_to_display = 10
split_text = '--split-here--'

# Main search query
# Note the addition of defType=edismax
# this is to use the edismax query parser, which will activate the relevancy tuning which uses the qf and bq params 
# Also note the fl (field list) - now we're storing the content for the highlighting it'll be faster to not return it
solr_main_search_query = 'select?defType=edismax&q={}&start={}&rows={}&wt=json&fl=url,title,description,contains_adverts&hl=on&hl.fl=content,description&hl.simple.pre={}&hl.simple.post={}&mm=2'
solr_main_search_query_groupbydomain = '&group=true&group.field=domain&group.limit=3&group.ngroups=true'

# Browse query - JSON Facet API
solr_facet_query = "query"
solr_facet_headers = {'Content-Type': 'text/json'}
base_payload_filter = ["is_home:true"]
payload = {
  "query": "*:*",
  "sort": "date_domain_added desc",
  "offset": 0,
  "limit": 10,
  "fields": ["title","url","domain","date_domain_added","tags"],
  "facet": {
    "site_category":                { "field": "site_category",                "type": "terms", "limit": 2, "sort": "count" },
    "tags":                         { "field": "tags",                         "type": "terms", "limit": 8, "sort": "count" },
    "owner_verified":               { "field": "owner_verified",               "type": "terms", "limit": 2, "sort": "count" },
    "contains_adverts":             { "field": "contains_adverts",             "type": "terms", "limit": 2, "sort": "count" },
    "indexed_inlink_domains_count": { "field": "indexed_inlink_domains_count", "type": "terms", "limit": 4, "sort": "index desc" },
    "language_primary":             { "field": "language_primary",             "type": "terms", "limit": 8, "sort": "count" }
  }
}

# Newest pages query. fq=published_date:* ensures there is a published_date
solr_newest_pages_query = 'select?q=*%3A*&fq=contains_adverts%3Afalse&fq=published_date%3A*&sort=published_date%20desc&start={}&rows={}&fl=url,title,description,published_date,tags'
solr_newest_pages_query_hlandgroupby = '&hl=on&hl.fl=content,description&hl.simple.pre={}&hl.simple.post={}&mm=2&group=true&group.field=domain&group.limit=1&group.ngroups=true'.format(split_text, split_text)

# Random result queries
random_result_step1_get_no_of_domains = 'select?q=*%3A*&rows=0&group=true&group.field=domain&group.limit=1&group.ngroups=true'
random_result_step2_get_domain_and_no_of_docs_on_domain = 'select?q=*%3A*&rows=1&group=true&group.field=domain&group.limit=1&group.ngroups=true&start={}&fl=domain'
random_result_step3_get_doc_from_domain = 'select?q=*%3A*&rows=1&start={}&fq=domain%3A{}'


@bp.route('/', methods=['GET', 'POST'])
def search(results = None):
    solrurl = config.SOLR_URL

    # Get params
    # With edismax, for the links that just have fq, i.e. have not q specified, we need to have q as * to get results
    # but we don't want to show * on the results screen
    query = request.args.get('q', '*')
    if query == '': query = '*' # for cases when when there is a q but no value, i.e. ?q=
    display_query = 'query = ' + query
    link_query = 'q=' + query
    groupbydomain = True
    if "domain:" in query:
        groupbydomain = False
    current_page = get_currentpage()

    # Get referrer
    referrer = request.referrer
    if not referrer:
        current_app.logger.info('No referrer set for the following search query: {}'.format(query))

    # Get search result
    start = get_start(current_page, results_per_page_search)
    solrquery = solr_main_search_query.format(quote(query), str(start), str(results_per_page_search), split_text, split_text)
    if groupbydomain:
        solrquery = solrquery + solr_main_search_query_groupbydomain
    connection = urlopen(solrurl + solrquery)
    response = json.load(connection)

    # Sort out pagination
    if groupbydomain:
        no_of_results_for_pagination = response['grouped']['domain']['ngroups'] 
        no_of_results_for_display = response['grouped']['domain']['matches']
    else:
        no_of_results_for_pagination = response['response']['numFound']
        no_of_results_for_display = no_of_results_for_pagination
    pages = get_page_range(current_page, no_of_results_for_pagination, results_per_page_search, max_pages_to_display)
    pagination = get_pagination(current_page, pages)

    # Construct the results list of result dicts for display.
    # If groupbydomain, the result dict will have subresults list of dicts.
    results = []
    if groupbydomain:
        for domain_results in response['grouped']['domain']['groups']:
            # The first result per domain should be represented in exactly the same format as if not groupbydomain
            first_result_from_domain = domain_results['doclist']['docs'][0]
            result = {}
            result['contains_adverts'] = first_result_from_domain['contains_adverts']
            result['url'] = first_result_from_domain['url']
            (full_title, short_title) = get_title(first_result_from_domain.get('title'), first_result_from_domain['url']) # title could be None, url is always set
            result['full_title'] = full_title
            result['short_title'] = short_title
            highlight = get_highlight(response['highlighting'], first_result_from_domain['url'], first_result_from_domain.get('description'))
            if highlight: result['highlight'] = highlight
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
                result['subresults_link'] = link_query + " %2Bdomain:" + subresults_domain # The + (%2B) before domain ensures that term is mandatory, otherwise multi word queries would treat the domain as optional
                result['subresults_link_text'] = "All " + str(subresults_total) + " results from " + subresults_domain
            results.append(result)
    else:
        for r in response['response']['docs']:
            result = {}
            result['contains_adverts'] = r['contains_adverts']
            result['url'] = r['url']
            (full_title, short_title) = get_title(r.get('title'), r['url']) # title could be None, url is always set
            result['full_title'] = full_title
            result['short_title'] = short_title
            highlight = get_highlight(response['highlighting'], r['url'], r.get('description'))
            if highlight: result['highlight'] = highlight
            results.append(result)
    return render_template('search/results.html', query=query, link_query=link_query, display_query=display_query, results=results, no_of_results_for_display=no_of_results_for_display, pagination=pagination, referrer=referrer)

@bp.route('/browse/', methods=['GET', 'POST'])
def browse(results = None):
    solrurl = config.SOLR_URL
    current_page = get_currentpage()
    start = get_start(current_page, results_per_page_browse)

    # Get params 1: sort order
    sort = "date_domain_added desc"
    if request.method == 'GET':
        sort = request.args.get('sort', "date_domain_added desc") # sort can also be date_domain_added%20asc, domain%20asc, domain%20desc
    else:
        sort = request.form.get('sort')

    # Get params 2: filter queries (a GET request won't have any)
    filter_queries = {} # this will be a dict with the facet name for the key and a list for the value
    if request.method == 'POST':
        keys = request.form.keys()
        for key in keys:
            if key != "sort" and key != "p": # sort and p (page number) are not facets 
                values = request.form.getlist(key)
                filter_queries[key] = values

    # Construct the fq list, of the form 'name:"value"' or 'name:("value1" AND "value2")'
    # Need the double quotes so values with spaces and odd characters such as : work
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

    # Get the results using the Facets JSON API
    solrquery = solrurl + solr_facet_query
    payload['filter'] = base_payload_filter + fq
    payload['sort'] = sort
    payload['offset'] = start
    payload['limit'] = results_per_page_browse
    solr_facet_payload = json.dumps(payload)
    req = Request(solrquery, solr_facet_payload.encode("utf8"), solr_facet_headers)
    response = urlopen(req)
    queryresults = json.load(response)
    no_of_domains = queryresults['response']['numFound']
    pages = get_page_range(current_page, no_of_domains, results_per_page_browse, max_pages_to_display)
    pagination = get_pagination(current_page, pages)

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
    facets = []
    for facet_field in queryresults['facets']:
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
            elif facet_field == "language_primary":
                facet['label_name'] = "Language"
            else:
                facet['label_name'] = facet_field
            inputs = []
            facet_values = queryresults['facets'][facet_field]['buckets']
            for facet_value in facet_values:
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

    # Construct the results list of dicts for rendering on the page
    results = []
    for queryresult in queryresults['response']['docs']:
        result = {}
        (full_title, short_title) = get_title(queryresult.get('title'), queryresult['url']) # title could be None, url is always set
        result['title'] = full_title
        result['short_title'] = short_title
        result['url'] = queryresult['url']
        result['domain'] = queryresult['domain']
        domain_added_string = queryresult['date_domain_added']
        domain_added_datetime = datetime.strptime(domain_added_string, "%Y-%m-%dT%H:%M:%SZ") # e.g. 2020-07-18T06:11:22Z
        result['date_domain_added'] = domain_added_datetime.strftime('%d %b %Y')# add ", %H:%M%z" for time
        tags_list = []
        if "tags" in queryresult:
            tags_list = queryresult['tags']
        tags_truncation_point = 10 # Just so the display doesn't get taken over by a site that does keyword stuffing
        if len(tags_list) > tags_truncation_point:
            result['tags'] = tags_list[:tags_truncation_point]
            result['tags_truncated'] = True
        else:
            result['tags'] = tags_list
            result['tags_truncated'] = False
        results.append(result)
    return render_template('search/browse.html', no_of_domains=no_of_domains, sort=sort, facets=facets, results=results, pagination=pagination)

# A stripped down version of search, using a different query (solr_newest_pages_query) but the same results page
@bp.route('/new/')
def newest(results = None):
    solrurl = config.SOLR_URL
    current_page = get_currentpage()
    start = get_start(current_page, results_per_page_newest)

    # Get results
    solrquery = solr_newest_pages_query.format(str(start), str(results_per_page_newest)) + solr_newest_pages_query_hlandgroupby
    connection = urlopen(solrurl + solrquery)
    response = json.load(connection)

    # Sort out pagination
    no_of_results_for_pagination = response['grouped']['domain']['ngroups'] 
    no_of_results_for_display = response['grouped']['domain']['matches']
    pages = get_page_range(current_page, no_of_results_for_pagination, results_per_page_newest, max_pages_to_display)
    pagination = get_pagination(current_page, pages)

    # Construct results list of discts
    results = []
    for domain_results in response['grouped']['domain']['groups']:
        # The first result per domain should be represented in exactly the same format as if not groupbydomain
        first_result_from_domain = domain_results['doclist']['docs'][0]
        result = {}
        result['url'] = first_result_from_domain['url']
        published_date_string = first_result_from_domain['published_date'] # there's a fq to ensure published_date is always present
        published_date_datetime = datetime.strptime(published_date_string, "%Y-%m-%dT%H:%M:%SZ") # e.g. 2020-07-18T06:11:22Z
        result['published_date'] = published_date_datetime.strftime('%d %b %Y')# add ", %H:%M%z" for time
        (full_title, short_title) = get_title(first_result_from_domain.get('title'), first_result_from_domain['url']) # title could be None, url is always set
        result['full_title'] = full_title
        result['short_title'] = short_title
        highlight = get_highlight(response['highlighting'], first_result_from_domain['url'], first_result_from_domain.get('description'))
        if highlight: result['highlight'] = highlight
        results.append(result)

    return render_template('search/results.html', no_of_results_for_display=no_of_results_for_display, results=results, pagination=pagination, referrer=request.referrer)

@bp.route('/random/')
def random():
    solrurl = config.SOLR_URL

    # Step 1: find out how many domains are in the collection
    solrquery = solrurl + random_result_step1_get_no_of_domains
    connection = urlopen(solrquery)
    response = json.load(connection)
    no_of_domains = response['grouped']['domain']['ngroups'] 

    # Step 2: pick a random domain and get the domain name and number of documents on that domain
    random_domain_number = randrange(no_of_domains)
    solrquery = solrurl + random_result_step2_get_domain_and_no_of_docs_on_domain.format(str(random_domain_number))
    connection = urlopen(solrquery)
    response = json.load(connection)
    domain_name = response['grouped']['domain']['groups'][0]['groupValue'] 
    no_of_docs_on_domain = response['grouped']['domain']['groups'][0]['doclist']['numFound']

    # Step 3: pick a random document form that domain
    random_document_number = randrange(no_of_docs_on_domain)
    solrquery = solrurl + random_result_step3_get_doc_from_domain.format(str(random_document_number), domain_name)
    connection = urlopen(solrquery)
    response = json.load(connection)
    url = response['response']['docs'][0]['url']

    # Step 4: return a redirect to that url
    return redirect(url, code=302)

def get_currentpage():
    if request.method == 'GET':
        current_page = request.args.get('p', 1)
    else:
        current_page = request.form.get('p')
    try:
        current_page = int(current_page)
    except:
        current_page = 1
    return current_page

def get_start(current_page, results_per_page):
    start = (current_page * results_per_page) - results_per_page # p1 is start 0, p2 is start 10, p3 is start 20 etc. if results_per_page = 10
    return start
    
def get_page_range(current_page, no_of_results, results_per_page, max_pages_to_display):
    last_results_page = int(math.ceil(no_of_results / results_per_page)) # round up to nearest int, so e.g. 11 results is 2 pages rather than 1
    # the following is from https://codereview.stackexchange.com/questions/92137/creating-a-page-number-array-for-pagination?rq=1
    range_start = max(min(current_page - (max_pages_to_display - 1) // 2, last_results_page - max_pages_to_display + 1), 1)
    range_end = min(max(current_page + max_pages_to_display // 2, max_pages_to_display), last_results_page) + 1
    return range(range_start, range_end)

def get_pagination(current_page, pages):
    pagination = {}
    #pagination = {"1": None, "2": "2", "3": "3"} # i.e. label and value for p link (None if no link)
    for page in pages:
        if page == current_page:
            pagination[page] = None
        else:
            pagination[page] = page
    return pagination

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
    if highlight: highlight = highlight.split(split_text) # Turn it into a list where highlight[1] is the highlighted term, so we wrap term in a <b> tag but HTML escape everything else 
    return highlight
