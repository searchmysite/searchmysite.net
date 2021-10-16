from flask import (
    Blueprint, request, current_app
)
from flask_restx import Resource, Namespace, Api, reqparse, fields, marshal_with, abort
from urllib.request import urlopen
from urllib.parse import urlencode
import psycopg2.extras
import json
import os
from searchmysite.db import get_db

bp = Blueprint('api', __name__)

api = Api(bp, version='1.0', title='Search My Site API', description='API for Search My Site search as a service')
ns = api.namespace("search", description="Search")

# /api/v1/search/<domain>?q=
# <domain> maps to fq=domain%3A<domain>
# q [query param]
# page [default 1 - generate solr's start via (current_page * rows) - rows]
# resultsperpage [default 10 - maps to solr's rows]
# sort [default score desc - maps to solr's sort]
# fields [default url, title, description, keywords, score]
parser = reqparse.RequestParser()
parser.add_argument('q', type=str, default="", help='Query string')
#parser.add_argument('filter', type=str, default="", help='Filter query for name=value')
parser.add_argument('page', type=int, default=1, help='Page number of results list')
parser.add_argument('resultsperpage', type=int, default=10, help='Number of results per page')
#parser.add_argument('fields', type=str, default="id,url,title,description,keywords,last_modified_date,language", help='Fields to include for each result')

solrquery = 'select?fl=id,url,title,author,description,tags,page_type,page_last_modified,published_date,language,indexed_inlinks,indexed_outlinks&q={}&start={}&rows={}&wt=json&fq=domain%3A{}'
# Fields not currently returned are: domain, is_home, content, date_domain_added, contains_adverts, owner_verified, indexed_inlinks_count, indexed_inlink_domains_count

sql_check_api_enabled = "SELECT api_enabled FROM tblDomains WHERE domain = (%s);"

#{
#  "params": {
#    "q": "*",
#    "page": 1,
#    "resultsperpage": 10,
#  }
#  "totalresults": 40,
#  "results": [
#    {
#      "id": "http://...",
#      "url": "http://...",
#      "title": "Michael Lewis's site",
#	...
#    }]
#}
results_fields = {
    'id': fields.String,
    'url': fields.String,
    'title': fields.String,
    'author': fields.String,
    'description': fields.String,
    'tags': fields.List(fields.String),
    'page_type': fields.String,
    'page_last_modified': fields.DateTime(dt_format='iso8601'),
    'published_date': fields.DateTime(dt_format='iso8601'),
    'language': fields.String,
    'indexed_inlinks': fields.List(fields.String),
    'indexed_outlinks': fields.List(fields.String),
}
resource_fields = api.model('Resource', {
})
resource_fields['params'] = {}
resource_fields['params']['q'] = fields.String
#resource_fields['params']['filter'] = fields.String(attribute='fq')
resource_fields['params']['page'] = fields.Integer
resource_fields['params']['resultsperpage'] = fields.Integer
#resource_fields['params']['fields'] = fields.String
resource_fields['totalresults'] = fields.Integer
resource_fields['results'] = fields.List(fields.Nested(results_fields, skip_none=True))


class SearchDao(object):
    #def __init__(self, q, fq, totalresults, page, resultsperpage, results):
    def __init__(self, q, totalresults, page, resultsperpage, results):
        self.q = q
        #self.fq = fq
        self.totalresults = totalresults
        self.page = page
        self.resultsperpage = resultsperpage
        #self.fields = fields
        self.results = results
        # This field will not be sent in the response
        self.status = 'active'

@ns.route("/<domain>")
class Search(Resource):
    @marshal_with(resource_fields)
    @api.doc(responses={
        200: 'Success',
        400: 'Validation Error'
    })
    @api.expect(parser)
    def get(self, domain):
        abort_if_api_not_enabled_for_domain(domain)
        # get params
        args = parser.parse_args(strict=True)
        q = args['q']
        #if 'filter' in args:
        #    fq = args['filter']
        #    fq_string = '&fq={}'.format(fq)
        #else:
        #    fq = ''
        #    fq_string = ''
        page = args['page']
        resultsperpage = args['resultsperpage']
        start = (page * resultsperpage) - resultsperpage
        #fields = args['fields']
        # do search
        solrurl = current_app.config['SOLR_URL']
        #queryurl = solrurl + solrquery.format(q, start, resultsperpage, domain, fq_string)
        queryurl = solrurl + solrquery.format(q, start, resultsperpage, domain)
        connection = urlopen(queryurl)
        response = json.load(connection)
        totalresults = response['response']['numFound']
        results = response['response']['docs']
        host = request.host_url
        origin = request.headers.get('Origin')
        if host.startswith('http://localhost') or host.startswith('https://localhost'):
            alloworigin = host # To save having to disable CORS for local testing
        elif origin and origin.endswith(domain):
            alloworigin = origin
        else:
            alloworigin = 'https://' + domain
        return SearchDao(q=q, totalresults=totalresults, page=page, resultsperpage=resultsperpage, results=results), 200, {'Access-Control-Allow-Origin': alloworigin}


# Return a 400 error is the API is not enabled for the domain
# Requires a database lookup for every API request, which isn't ideal
def abort_if_api_not_enabled_for_domain(domain):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(sql_check_api_enabled, (domain,))
    result = cursor.fetchone()
    if result['api_enabled'] == True:
        api_enabled_for_domain = True
    else:
        api_enabled_for_domain = False
    if not api_enabled_for_domain:
        abort(400, message="Domain {} does not have the API enabled".format(domain))
