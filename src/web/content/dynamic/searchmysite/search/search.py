from flask import Flask, request, url_for, render_template, redirect, Blueprint, current_app
from urllib.request import urlopen, Request
from urllib.parse import quote, unquote
from os import environ
import json
import math
from random import randrange
from datetime import datetime, date
import config
import searchmysite.solr
from searchmysite.searchutils import get_search_params, get_start, get_filter_queries, do_search, get_no_of_results, get_page_range, get_links, get_display_pagination, get_display_facets, get_display_results

bp = Blueprint('search', __name__)


@bp.route('/', methods=['GET', 'POST'])
def search(search_type='search'):

    # Get params and data required to perform search
    params = get_search_params(request, search_type)
    groupbydomain = False if "domain:" in params['q'] else True
    start = get_start(params)
    filter_queries = get_filter_queries(params['filter_queries'])

    # Perform the actual search
    search_results = do_search(searchmysite.solr.query_params_search, searchmysite.solr.query_facets_search, params, start, searchmysite.solr.mandatory_filter_queries_search, filter_queries, groupbydomain)

    # Get data required to display the results
    (total_results, total_domains) = get_no_of_results(search_results, groupbydomain)
    page_range = get_page_range(params['page'], total_domains, searchmysite.solr.default_results_per_page_search, searchmysite.solr.max_pages_to_display)
    links = get_links(request, params, search_type)
    display_pagination = get_display_pagination(params['page'], page_range)
    display_facets = get_display_facets(params['filter_queries'], search_results)
    display_results = get_display_results(search_results, groupbydomain, params, links['query_string'])

    return render_template('search/results.html', params=params, facets=display_facets, sort_options=searchmysite.solr.sort_options_search, results=display_results, no_of_results=total_results, pagination=display_pagination, links=links, display_type='list', subtitle='Search Results')


@bp.route('/browse/', methods=['GET', 'POST'])
def browse(search_type='browse'):

    # Get params and data required to perform search
    params = get_search_params(request, search_type)
    groupbydomain = False # Browse only returns home pages, so will only have one result per domain
    start = get_start(params)
    filter_queries = get_filter_queries(params['filter_queries'])

    # Perform the actual search
    search_results = do_search(searchmysite.solr.query_params_browse, searchmysite.solr.query_facets_browse, params, start, searchmysite.solr.mandatory_filter_queries_browse, filter_queries, groupbydomain)

    # Get data required to display the results
    (total_results, _) = get_no_of_results(search_results, groupbydomain) # groupbydomain False so both values will be the same
    page_range = get_page_range(params['page'], total_results, searchmysite.solr.default_results_per_page_browse, searchmysite.solr.max_pages_to_display)
    links = get_links(request, params, search_type)
    display_pagination = get_display_pagination(params['page'], page_range)
    display_facets = get_display_facets(params['filter_queries'], search_results)
    display_results = get_display_results(search_results, groupbydomain, params, links['query_string'])

    return render_template('search/results.html', params=params, facets=display_facets, sort_options=searchmysite.solr.sort_options_browse, results=display_results, no_of_domains=total_results, pagination=display_pagination, links=links, display_type='table', subtitle='Browse Sites')


@bp.route('/new/', methods=['GET', 'POST'])
def newest(search_type='newest'):

    # Get params and data required to perform search
    params = get_search_params(request, search_type)
    groupbydomain = True # There is a group by domain in the query, even though only 1 result is returned for each domain - this is to ensure only one result per domain in the feed
    start = get_start(params)
    filter_queries = get_filter_queries(params['filter_queries'])

    # Perform the actual search
    search_results = do_search(searchmysite.solr.query_params_newest, searchmysite.solr.query_facets_newest, params, start, searchmysite.solr.mandatory_filter_queries_newest, filter_queries, groupbydomain)

    # Get data required to display the results
    (_, total_domains) = get_no_of_results(search_results, groupbydomain) # Need to use the total_domains, given 1 result per domain
    page_range = get_page_range(params['page'], total_domains, searchmysite.solr.default_results_per_page_newest, searchmysite.solr.max_pages_to_display)
    links = get_links(request, params, search_type)
    display_pagination = get_display_pagination(params['page'], page_range)
    display_facets = get_display_facets(params['filter_queries'], search_results)
    display_results = get_display_results(search_results, groupbydomain, params, links['query_string'])

    return render_template('search/results.html', params=params, facets=display_facets, sort_options=searchmysite.solr.sort_options_newest, results=display_results, no_of_results=total_domains, pagination=display_pagination, links=links, display_type='list', subtitle='Newest Pages')


@bp.route('/random/')
def random():
    solrurl = config.SOLR_URL

    # Step 1: find out how many domains are in the collection
    solrquery = solrurl + searchmysite.solr.random_result_step1_get_no_of_domains
    connection = urlopen(solrquery)
    response = json.load(connection)
    no_of_domains = response['grouped']['domain']['ngroups'] 

    # Step 2: pick a random domain and get the domain name and number of documents on that domain
    random_domain_number = randrange(no_of_domains)
    solrquery = solrurl + searchmysite.solr.random_result_step2_get_domain_and_no_of_docs_on_domain.format(str(random_domain_number))
    connection = urlopen(solrquery)
    response = json.load(connection)
    domain_name = response['grouped']['domain']['groups'][0]['groupValue'] 
    no_of_docs_on_domain = response['grouped']['domain']['groups'][0]['doclist']['numFound']

    # Step 3: pick a random document from that domain
    random_document_number = randrange(no_of_docs_on_domain)
    solrquery = solrurl + searchmysite.solr.random_result_step3_get_doc_from_domain.format(str(random_document_number), domain_name)
    connection = urlopen(solrquery)
    response = json.load(connection)
    url = response['response']['docs'][0]['url']

    # Step 4: return a redirect to that url
    return redirect(url, code=302)
