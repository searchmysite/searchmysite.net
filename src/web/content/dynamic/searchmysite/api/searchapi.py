from flask import (
    Blueprint, jsonify, request, current_app, make_response
)
from urllib.request import urlopen
from urllib.parse import quote
from datetime import datetime
import psycopg2.extras
import json
import os
from searchmysite.db import get_db

bp = Blueprint('api', __name__)

split_text = '--split-here--'
solrquery = 'select?fl=id,url,title,author,description,tags,page_type,page_last_modified,published_date,language,indexed_inlinks,indexed_outlinks&q={}&start={}&rows={}&wt=json&fq=domain%3A{}&hl=on&hl.fl=content&hl.simple.pre={}&hl.simple.post={}'

sql_check_api_enabled = "SELECT api_enabled FROM tblDomains WHERE domain = (%s);"

# Full URL:
#   /api/v1/search/<domain>?q=<query>
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
def search(domain):
    api_enabled = check_if_api_enabled_for_domain(domain)
    if api_enabled is None:
        return error_response(404, message="Domain {} not found".format(domain))
    elif api_enabled is False:
        return error_response(400, message="Domain {} does not have the API enabled".format(domain))
    else:
        # Get params
        query = request.args.get('q', '*')
        if query == '': query = '*'
        page = request.args.get('page', 1)
        try:
            page = int(page)
        except:
            page = 1
        resultsperpage = request.args.get('resultsperpage', 10)
        try:
            resultsperpage = int(resultsperpage)
        except:
            resultsperpage = 10
        start = (page * resultsperpage) - resultsperpage
        # Do search
        solrurl = current_app.config['SOLR_URL']
        queryurl = solrurl + solrquery.format(quote(query), start, resultsperpage, domain, split_text, split_text)
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
            if response['highlighting'][url]:
                result['fragment'] = response['highlighting'][url]['content'][0].split(split_text)
        # Construct results response
        current_app.config['JSON_SORT_KEYS'] = False # Make sure the order is preserved (not essential, but I like seeing e.g. params before results and id as the first value in results)
        response = {}
        params = {}
        params['q'] = query
        params['page'] = page
        params['resultsperpage'] = resultsperpage
        response['params'] = params
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

# Checks if the API is enabled or not for a domain
# Returns True or False, or None is the domain isn't found
# Requires a database lookup for every API request, which isn't ideal
def check_if_api_enabled_for_domain(domain):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_check_api_enabled, (domain,))
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

def error_response(status_code, message=None):
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
