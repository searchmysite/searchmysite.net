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
from searchmysite.searchutils import get_search_params, get_start, get_filter_queries, do_search, get_no_of_results, get_page_range, get_link, get_display_pagination, get_display_facets, get_display_results

bp = Blueprint('search', __name__)


@bp.route('/', methods=['GET', 'POST'])
def search(results = None):

    # Get params and data required to perform search
    params = get_search_params(request)
    groupbydomain = False if "domain:" in params['q'] else True
    start = get_start(params['page'], searchmysite.solr.default_results_per_page_search)
    filter_queries = get_filter_queries(params['filter_queries'])

    # Perform the actual search
    search_results = do_search(searchmysite.solr.query_params_search, searchmysite.solr.query_facets_search, params, start, searchmysite.solr.mandatory_filter_queries_search, filter_queries, groupbydomain)

    # Get data required to display the results
    (no_of_results_for_pagination, no_of_results_for_display) = get_no_of_results(search_results, groupbydomain)
    page_range = get_page_range(params['page'], no_of_results_for_pagination, searchmysite.solr.default_results_per_page_search, searchmysite.solr.max_pages_to_display)
    link = get_link(params['q'], params['filter_queries'], params['sort'], searchmysite.solr.default_sort_search)
    display_pagination = get_display_pagination(params['page'], page_range)
    display_facets = get_display_facets(params['filter_queries'], search_results)
    display_results = get_display_results(search_results, groupbydomain, params, link)

    return render_template('search/results.html', params=params, facets=display_facets, sort_options=searchmysite.solr.sort_options_search, results=display_results, no_of_results=no_of_results_for_display, pagination=display_pagination, display_type='list')


@bp.route('/browse/', methods=['GET', 'POST'])
def browse(results = None):

    # Get params and data required to perform search
    params = get_search_params(request)
    groupbydomain = False # Browse only returns home pages, so will only have one result per domain
    start = get_start(params['page'], searchmysite.solr.default_results_per_page_browse)
    filter_queries = get_filter_queries(params['filter_queries'])

    # Perform the actual search
    search_results = do_search(searchmysite.solr.query_params_browse, searchmysite.solr.query_facets_browse, params, start, searchmysite.solr.mandatory_filter_queries_browse, filter_queries, groupbydomain)

    # Get data required to display the results
    (no_of_domains, _) = get_no_of_results(search_results, groupbydomain) # groupbydomain False so both values will be the same, i.e. second response ignored
    page_range = get_page_range(params['page'], no_of_domains, searchmysite.solr.default_results_per_page_browse, searchmysite.solr.max_pages_to_display)
    link = get_link(params['q'], params['filter_queries'], params['sort'], searchmysite.solr.default_sort_search)
    display_pagination = get_display_pagination(params['page'], page_range)
    display_facets = get_display_facets(params['filter_queries'], search_results)
    display_results = get_display_results(search_results, groupbydomain, params, link)

    return render_template('search/results.html', params=params, facets=display_facets, sort_options=searchmysite.solr.sort_options_browse, results=display_results, no_of_domains=no_of_domains, pagination=display_pagination,  display_type='table')


@bp.route('/new/', methods=['GET', 'POST'])
def newest(results = None):

    # Get params and data required to perform search
    params = get_search_params(request)
    groupbydomain = True # Although only 1 results is returned for each domain
    start = get_start(params['page'], searchmysite.solr.default_results_per_page_newest)
    filter_queries = get_filter_queries(params['filter_queries'])

    # Perform the actual search
    search_results = do_search(searchmysite.solr.query_params_newest, searchmysite.solr.query_facets_newest, params, start, searchmysite.solr.mandatory_filter_queries_newest, filter_queries, groupbydomain)

    # Get data required to display the results
    (no_of_results_for_pagination, no_of_results_for_display) = get_no_of_results(search_results, groupbydomain)
    page_range = get_page_range(params['page'], no_of_results_for_pagination, searchmysite.solr.default_results_per_page_newest, searchmysite.solr.max_pages_to_display)
    link = get_link(params['q'], params['filter_queries'], params['sort'], searchmysite.solr.default_sort_newest)
    display_pagination = get_display_pagination(params['page'], page_range)
    display_facets = get_display_facets(params['filter_queries'], search_results)
    display_results = get_display_results(search_results, groupbydomain, params, link)

    current_app.logger.info('params: {}, sort_options_newest: {}'.format(params, searchmysite.solr.sort_options_newest))

    return render_template('search/results.html', params=params, facets=display_facets, sort_options=searchmysite.solr.sort_options_newest, results=display_results, no_of_results=no_of_results_for_display, pagination=display_pagination, display_type='list')


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
