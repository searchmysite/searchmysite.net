from flask import (
    Blueprint, jsonify, request, current_app, make_response
)
from urllib.request import urlopen
from urllib.parse import quote
from datetime import datetime, timezone
import json
import xml.etree.ElementTree as ET
import xml.dom.minidom
from searchmysite.db import get_db
import config
import searchmysite.solr
from searchmysite.searchutils import check_if_api_enabled_for_domain, get_search_params, get_filter_queries, get_start, do_search, get_no_of_results, get_links, get_display_results, do_vector_search, get_query_vector_string
import requests


bp = Blueprint('searchapi', __name__)

# Site specific JSON API
# ---------------------- 
# 
# Full URL:
#   /api/v1/search/<domain>?q=<query>
#   e.g. /api/v1/search/michael-lewis.com?q=*
#
# Parameters:
#   <domain>: the domain being searched (mandatory)
#   q: query string (mandatory, default *)
#   page: the page number from which multi-page results should start (optional, default 1)
#   resultsperpage: the number of results per page (optional, default 10)
#
# Responses:
#   Domain not found:
#     404 {"message": "Domain <domain> not found"}
#   Domain does not have API enabled:
#     400 {"message": "Domain <domain> does not have the API enabled"}
#   No results:
#     200 {"params": {"q": "<query>", "page": 1, "resultsperpage": 10}, "totalresults": 0, "results": []}
#   Results:
#{
#  "params": {
#    "q": "*",
#    "page": 1,
#    "resultsperpage": 10,
#  }
#  "totalresults": 40,
#  "results": [
#    {
#      "id": "https://server/path",
#      "url": "https://server/path",
#      "title": "Page title",
#      "author": "Author",
#      "description": "Page description",
#      "tags": ["tag1", "tag2"],
#      "page_type": "Page type, e.g. article",
#      "page_last_modified": "2020-07-17T00:00:00+00:00",
#      "published_date": "2020-07-17T00:00:00+00:00",
#      "language": "en",
#      "indexed_inlinks": ["inlink1", "inlink2"],
#      "indexed_outlinks": ["outlink1", "outlink2"],
#      "fragment": ["text before the search ", "query", " and text after"]
#    }
#  ]
#}
#
@bp.route('/search/<domain>', methods=['GET']) # the /api/v1 URL prefix is set in ../__init__.py
def search(domain, search_type='search'):
    api_enabled = check_if_api_enabled_for_domain(domain)
    if api_enabled is None:
        return error_response(404, 'json', message="Domain {} not found".format(domain))
    elif api_enabled is False:
        return error_response(400, 'json', message="Domain {} does not have the API enabled".format(domain))
    else:
        # Get params
        params = get_search_params(request, search_type)
        start = get_start(params)
        # Do search
        solrurl = config.SOLR_URL
        queryurl = solrurl + searchmysite.solr.solrquery.format(quote(params['q']), start, params['resultsperpage'], domain, searchmysite.solr.split_text, searchmysite.solr.split_text)
        connection = urlopen(queryurl)
        response = json.load(connection)
        # Process results, i.e. get data, reformat dates, and add fragment
        totalresults = response['response']['numFound']
        results = response['response']['docs']
        for result in results:
            if 'page_last_modified' in result:
                result['page_last_modified'] = convert_java_utc_string_to_python_utc_string(result['page_last_modified'])
            if 'published_date' in result:
                result['published_date'] = convert_java_utc_string_to_python_utc_string(result['published_date'])
            url = result['url']
            if url in response['highlighting'] and response['highlighting'][url]:
                result['fragment'] = response['highlighting'][url]['content'][0].split(searchmysite.solr.split_text)
        # Construct results response
        current_app.config['JSON_SORT_KEYS'] = False # Make sure the order is preserved (not essential, but I like seeing e.g. params before results and id as the first value in results)
        response = {}
        p = {}
        p['q'] = params['q']
        p['page'] = params['page']
        p['resultsperpage'] = params['resultsperpage']
        response['params'] = p
        response['totalresults'] = totalresults
        response['results'] = results
        # Add the Access-Control-Allow-Origin header
        host = request.host_url
        origin = request.headers.get('Origin')
        if host.startswith('http://localhost') or host.startswith('https://localhost'):
            alloworigin = host # To save having to disable CORS for local testing
        elif origin and origin.endswith(domain):
            alloworigin = origin
        else:
            alloworigin = 'https://' + domain
        # Return
        resp = make_response(jsonify(response))
        resp.headers['Access-Control-Allow-Origin'] = alloworigin
        return resp


# OpenSearch Atom responses
# -------------------------
# 
# Full URL:
#   /api/v1/<format>/search/?q=<query>
#   e.g. /api/v1/feed/search/?q=*
# 
# Parameters:
#   <format> is the root node name - just 'feed' (for Atom 1.0) is supported for now, but 'rss' (for RSS 2.0) could be added
#   q, and other parameters, are exactly the same as those for /search
# 
# Responses:
#   Format not found:
#     404 <message>/.../search not found</message>
#   Results:
#     As per spec at https://github.com/dewitt/opensearch/blob/master/opensearch-1-1-draft-6.md#opensearch-response-elements
#     Note that results should be exactly the same as those from the equivalent query to /search.
#     In fact any request starting /search/ should have the exact equivalent with /api/v1/feed added in front of /search/
#     including /search/browse/ etc.
#
@bp.route('/<format>/search/', methods=['GET', 'POST'])
def feed_search(format, search_type='search'):
    if format == 'feed':
        params = get_search_params(request, search_type)
        groupbydomain = False if "domain:" in params['q'] else True
        start = get_start(params)
        filter_queries = get_filter_queries(params['filter_queries'])
        search_results = do_search(searchmysite.solr.query_params_search, searchmysite.solr.query_facets_search, params, start, searchmysite.solr.mandatory_filter_queries_search, filter_queries, groupbydomain)
        (total_results, _) = get_no_of_results(search_results, groupbydomain)
        links = get_links(request, params, search_type)
        results = get_display_results(search_results, groupbydomain, params, links['query_string'])
        xml_string = convert_results_to_xml_string(results, params, total_results, links, search_type)
        resp = make_response(xml_string)
        resp.headers['Content-Type'] = 'application/atom+xml; charset=utf-8'
        return resp
    else:
        return error_response(404, 'xml', message="/{}/search/ not found".format(format))

@bp.route('/<format>/search/browse/', methods=['GET', 'POST'])
def feed_browse(format, search_type='browse'):
    if format == 'feed':
        params = get_search_params(request, search_type)
        groupbydomain = False # Browse only returns home pages, so will only have one result per domain
        start = get_start(params)
        filter_queries = get_filter_queries(params['filter_queries'])
        search_results = do_search(searchmysite.solr.query_params_browse, searchmysite.solr.query_facets_browse, params, start, searchmysite.solr.mandatory_filter_queries_browse, filter_queries, groupbydomain)
        (total_results, _) = get_no_of_results(search_results, groupbydomain)
        links = get_links(request, params, search_type)
        results = get_display_results(search_results, groupbydomain, params, links['query_string'])
        xml_string = convert_results_to_xml_string(results, params, total_results, links, search_type)
        resp = make_response(xml_string)
        resp.headers['Content-Type'] = 'application/atom+xml; charset=utf-8'
        return resp
    else:
        return error_response(404, 'xml', message="/{}/search/browse/ not found".format(format))

@bp.route('/<format>/search/new/', methods=['GET', 'POST'])
def feed_newest(format, search_type='newest'):
    if format == 'feed':
        params = get_search_params(request, search_type)
        groupbydomain = True # There is a group by domain in the query, even though only 1 result is returned for each domain - this is to ensure only one result per domain in the feed
        start = get_start(params)
        filter_queries = get_filter_queries(params['filter_queries'])
        search_results = do_search(searchmysite.solr.query_params_newest, searchmysite.solr.query_facets_newest, params, start, searchmysite.solr.mandatory_filter_queries_newest, filter_queries, groupbydomain)
        (_, total_domains) = get_no_of_results(search_results, groupbydomain) # Need to use the no_of_results_for_pagination, given 1 result per domain
        links = get_links(request, params, search_type)
        results = get_display_results(search_results, groupbydomain, params, links['query_string'])
        xml_string = convert_results_to_xml_string(results, params, total_domains, links, search_type)
        resp = make_response(xml_string)
        resp.headers['Content-Type'] = 'application/atom+xml; charset=utf-8'
        return resp
    else:
        return error_response(404, 'xml', message="/{}/search/browse/ not found".format(format))


# Vector search API
# -----------------
# 
# Full URL:
#   /api/v1/knnsearch/?q=<query>&domain=<domain>
#   e.g. /api/v1/feed/search/?q=What%20is%20vector%20search&domain=*
# 
# Parameters:
#   <query> is the query text
#   <domain> is the domain to search, or * for all domains
# 
# Responses:
#   Results:
#    [
#     {'id': 'https://url/!chunk010', 
#      'content_chunk_text': '...',
#      'url': 'https://url/',
#      'score': 0.8489073},
#     {...}, ...
#    ]
#
#
@bp.route('/knnsearch/', methods=['GET', 'POST'])
def vector_search():
    params = get_search_params(request, 'search')
    query = params['q']
    domain = params['domain']
    query_vector_string = get_query_vector_string(query)
    response = do_vector_search(query_vector_string, domain)
    results = response['response']['docs']
    #current_app.logger.debug('results: {}'.format(results))
    return results


# LLM Vector search API
# ---------------------
# 
# Full URL:
#   /api/v1/predictions/llm/?q=<query>&prompt=<domain>&context=<context>
#   e.g. /api/v1/predictions/llm/?q=How%20long%20does%20it%20take%20to%20climb%20Ben%20Nevis&prompt=qa&context=it%20took%204%20hours%20to%20climb%20ben%20nevis
# 
# Parameters:
#   <query> is the query text
#   <prompt> indicates the prompt template to use, e.g. "qa" for question answering
#   <context> is the context text for the prompt template
# 
# Responses:
#   Results:
#     Text
#

@bp.route('/predictions/llm', methods=['GET', 'POST'])
def predictions():
    # Get data from request
    if request.method == 'GET':
        query = request.args.get('q', '')
        context = request.args.get('context', '')
        prompt_type = request.args.get('prompt', 'qa')
    else: # i.e. if POST
        query = request.json['q']
        context = request.json['context']
        prompt_type = request.json['prompt']
    # Build LLM prompt
    # prompt_format is "chatml" for ChatML format, or "llama2-chat" for the Llama 2 Chat format
    prompt_format = "llama2-chat"
    llm_prompt = get_llm_prompt(query, context, prompt_type, prompt_format)
    llm_data = get_llm_data(llm_prompt)
    #current_app.logger.debug('llm_prompt: {}'.format(llm_prompt))
    # Do request
    response = do_llm_prediction(llm_prompt, llm_data)
    return make_response(jsonify(response))

def get_llm_prompt(question, context, prompt_type, prompt_format):
    if prompt_type == 'qa':
        system = "Answer the question based on the context below."
        if prompt_format == 'llama2-chat':
            prompt = "<s>[INST] <<SYS>>{system}<</SYS>> \n [context]: {context} \n [question]: {question} [\INST]".format(system=system, context=context, question=question)
        else:
            prompt = "<|im_start|>system\n{system}<|im_end|><|im_start|>user\nContext:{context} Question: {question}<|im_end|>\n<|im_start|>assistant".format(system=system, context=context, question=question)
    else:
        prompt = "[INST] <<SYS>> You are a helpful, respectful and honest assistant. Always answer as helpfully as possible, while being safe. If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. If you don't know the answer to a question, please don't share false information.<</SYS>>{}[/INST]".format(query)
    return prompt

def get_llm_data(prompt):
    data = json.dumps(
        {
            "prompt": prompt,
            "max_tokens": 100,
            "top_p": 0.95,
            "temperature": 0.8,
        }
    )
    return data

def do_llm_prediction(prompt, data):
    url = config.TORCHSERVE + "predictions/llama2"
    headers = {"Content-type": "application/json", "Accept": "text/plain"}
    response = requests.post(url=url, data=data, headers=headers)
    cleaned_response = response.text.removeprefix(prompt)
    return cleaned_response     


# Utilities

def convert_results_to_xml_string(results, params, no_of_results_for_display, links, search_type):
    root = ET.Element('feed', attrib={'xmlns':'http://www.w3.org/2005/Atom', 'xmlns:opensearch':'http://a9.com/-/spec/opensearch/1.1/'})
    ET.SubElement(root, 'title').text = 'searchmysite.net results'
    ET.SubElement(root, 'id').text = 'https://searchmysite.net/'
    ET.SubElement(root, 'updated').text = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    ET.SubElement(root, 'opensearch:totalResults').text = str(no_of_results_for_display)
    ET.SubElement(root, 'opensearch:startIndex').text = str(params['page'])
    ET.SubElement(root, 'opensearch:itemsPerPage').text = str(params['resultsperpage'])
    if search_type == 'search': ET.SubElement(root, 'opensearch:Query', attrib={'role':'request', 'searchTerms':params['q']}) # /search/browse/ and /search/new/ don't have query strings
    ET.SubElement(root, 'link', attrib={'rel':'alternate', 'href':links['full_link'], 'type':'text/html'})
    ET.SubElement(root, 'link', attrib={'rel':'self', 'href':links['full_feed_link'], 'type':'application/atom+xml'})
    ET.SubElement(root, 'link', attrib={'rel':'search', 'href':links['opensearchdescription'], 'type':'application/opensearchdescription+xml'})
    for result in results:
        entry = ET.SubElement(root, 'entry')
        ET.SubElement(entry, 'title').text = result['full_title']
        ET.SubElement(entry, 'link', attrib={'href':result['url']})
        ET.SubElement(entry, 'id').text = result['id']
        if 'page_last_modified' in result: ET.SubElement(entry, 'updated').text = result['page_last_modified'] # Note that updated should be mandatory according to https://validator.w3.org/feed/docs/atom.html but not all pages have this value set
        if 'published_datetime' in result: ET.SubElement(entry, 'published').text = result['published_datetime']
        if 'highlight' in result: ET.SubElement(entry, 'summary',  attrib={'type':'text'}).text = ''.join(result['highlight'])
    dom = xml.dom.minidom.parseString(ET.tostring(root, encoding='utf-8', method='xml'))
    xml_string = dom.toprettyxml(encoding="utf-8")
    return xml_string

def error_response(status_code, type, message=None):
    if type == 'xml':
        payload = ET.Element('message')#.text = message
        payload.text = message
        dom = xml.dom.minidom.parseString(ET.tostring(payload))
        xml_string = dom.toprettyxml(encoding="UTF-8")
        response = make_response(xml_string)
    else:
        #payload = {'error': HTTP_STATUS_CODES.get(status_code, 'Unknown error')}
        payload = {}
        if message:
            payload['message'] = message
        response = jsonify(payload)
    response.status_code = status_code
    return response

# Convert the UTC time returned by Solr in Java's DateTimeFormatter.ISO_INSTANT format,
# i.e. YYYY-MM-DDThh:mm:ssZ      e.g. 2022-08-14T14:50:45Z
# to Python's UTC time in ISO 8601 format
# i.e. YYYY-MM-DDThh:mm:ss+00:00 e.g. 2022-08-14T14:50:45+00:00
def convert_java_utc_string_to_python_utc_string(input):
    output = datetime.strptime(input, "%Y-%m-%dT%H:%M:%S%z").isoformat()
    return output
