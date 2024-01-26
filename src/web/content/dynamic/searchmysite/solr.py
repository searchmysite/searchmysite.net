# Search config, (defaults etc.)
# ------------------------------

max_pages_to_display = 10
default_results_per_page_search = 10
default_results_per_page_browse = 20
default_results_per_page_newest = 12
default_results_per_page_api = 10
sort_options_search = {"score desc": "Score (high-low)", "published_date desc": "Published (new-old)", "page_last_modified desc": "Modified (new-old)"}
sort_options_browse = {"date_domain_added desc": "Added (new-old)", "date_domain_added asc": "Added (old-new)", "domain asc": "Domain (A-Z)", "domain desc": "Domain (Z-A)", "indexed_inlink_domains_count desc": "Inlinks (high-low)"}
sort_options_newest = {"published_date desc": "Published (new-old)", "published_date asc": "Published (old-new)", "page_last_modified desc": "Modified (new-old)"}
default_sort_search = "score desc"
default_sort_browse = "date_domain_added desc"
default_sort_newest = "published_date desc"
mandatory_filter_queries_search = ["public:true", "!content_type:*xml", "!content_type:application*", "!content_type:binary*"]
mandatory_filter_queries_browse = ["public:true", "is_home:true"]
mandatory_filter_queries_newest = mandatory_filter_queries_search + ["contains_adverts:false", "published_date:[NOW-30YEARS TO NOW]", "is_home:false"] # to ensure no future dates or infeasibly far past dates, and no home pages
split_text = '--split-here--'
solr_request_handler = "select" # The custom config in solrconfig.xml, especially the relevancy tuning, is only set for the select request handler 
solr_request_headers = {'Content-Type': 'text/json'}


# Solr search queries
# -------------------

# There are 5 search queries. The main differences are the mandatory filter queries:
# 1. Main search, i.e. queries from the search box. This has to show only public content, and filters out non-web friendly results.
# 2. Browse Sites search. This has to show only public content, and only home pages.
# 3. Newest Pages search. This is as per the main search, but also filters out pages that might not be posts and sorts by date.
# 4. Random Page search. This is actually 3 sub searches, to find no of sites, no of pages in random site, and details of random page.
# 5. Site specific API. This is only returned for site where api_enabled, but will return all content in the site (it is down to users to filter).

# 1. Main search query
# Notes:
# a. defType:edismax is to use the edismax query parser, required for the relevancy tuning defined in solrconfig.xml. edismax
#    (or dismax) is required because the relevancy tuning uses qf and pf which aren't available in the default lucene query parser.
# b. mm:2 is must match two words, applicable when the query contains more than two words, so e.g. "book about antarctica" 
#    (without the double quotes) will require book and antarctica but not just book.
# c. fq is to ensure the public search only contains results marked for the public search and filters out "non web friendly"
#    results like XML and binary files.
# d. group:True is set to False if the query contains domain:<domain>, i.e. someone is searching for content on a specific domain.
#    The other group params will be irrelevant when group:False.
query_params_search = {
    "q": "*:*",
    "defType": "edismax",
    "mm": 2,
    "start": 0,
    "rows": default_results_per_page_search,
    "sort": default_sort_search,
    "fl": ["id", "url", "title", "description", "contains_adverts", "published_date"],
    "q.op": "AND",
    "fq": mandatory_filter_queries_search,
    "hl": True,
    "hl.fl": ["content", "description"],
    "hl.method": "original", # default is "original" in Sol 8 but "unified" in Solr 9. Unfortunately "unified" in Solr 9.0 seems to ignore hl.fragsize
    "hl.fragsize": 100,
    "hl.simple.pre": split_text,
    "hl.simple.post": split_text,
    "group": True,
    "group.field": "domain",
    "group.limit": 3,
    "group.ngroups": True
}

query_facets_search = {
    "site_category":                { "field": "site_category",                "type": "terms", "limit":  2, "sort": "count" },
    "domain":                       { "field": "domain",                       "type": "terms", "limit":  6, "sort": "count" },
    "in_web_feed":                  { "field": "in_web_feed",                  "type": "terms", "limit":  2, "sort": "count" },
    "language_primary":             { "field": "language_primary",             "type": "terms", "limit": 20, "sort": "count" }
}

# 2. Browse query
# Notes:
# a. Don't need to specify the query parser because browse just has simple ordering with no custom config, e.g. relevancy tuning, required.
# b. The fq is the base filter query that must always be present on browse - it may be supplemented by values selected in the filters.
query_params_browse = {
    "q": "*:*",
    "start": 0,
    "rows": default_results_per_page_browse,
    "sort": default_sort_browse,
    "fl": ["id", "url", "title", "domain", "date_domain_added", "tags", "web_feed"],
    "fq": mandatory_filter_queries_browse
}
query_facets_browse = {
    "site_category":                { "field": "site_category",                "type": "terms", "limit": 2, "sort": "count" },
    "tags":                         { "field": "tags",                         "type": "terms", "limit": 8, "sort": "count" },
    "owner_verified":               { "field": "owner_verified",               "type": "terms", "limit": 2, "sort": "count" },
    "contains_adverts":             { "field": "contains_adverts",             "type": "terms", "limit": 2, "sort": "count" },
    "indexed_inlink_domains_count": { "field": "indexed_inlink_domains_count", "type": "terms", "limit": 4, "sort": "index desc" },
    "language_primary":             { "field": "language_primary",             "type": "terms", "limit": 8, "sort": "count" }
}

# 3. Newest pages query
# Notes:
# a. The fq is as per the main search, but also ensures there is a published_date and excludes pages with adverts from this feed
# b. The group is to ensure only one result per domain (to prevent any one domain from dominating the feed)
query_params_newest = {
    "q": "*:*",
    "defType": "edismax",
    "mm": 2,
    "start": 0,
    "rows": default_results_per_page_newest,
    "sort": default_sort_newest,
    "fl": ["id", "url", "title", "description", "published_date", "tags"],
    "fq": mandatory_filter_queries_newest,
    "hl": "on",
    "hl.fl": ["content", "description"],
    "hl.simple.pre": split_text,
    "hl.simple.post": split_text,
    "group": True,
    "group.field": "domain",
    "group.limit": 1,
    "group.ngroups": True
}
query_facets_newest = query_facets_search

# 4. Random result queries
query_filter_public = '&fq=public%3Atrue'
query_filter_content_type = '&fq=!content_type%3A*xml&fq=!content_type%3Aapplication*&fq=!content_type%3Abinary*'
query_groupbydomain = '&group=true&group.field=domain&group.limit={}&group.ngroups=true'
random_result_step1_get_no_of_domains = 'select?q=*%3A*&rows=0' + query_filter_public + query_groupbydomain.format('1')
random_result_step2_get_domain_and_no_of_docs_on_domain = 'select?q=*%3A*&rows=1&start={}&fl=domain' + query_filter_content_type + query_filter_public + query_groupbydomain.format('1')
random_result_step3_get_doc_from_domain = 'select?q=*%3A*&rows=1&start={}&fq=domain%3A{}' + query_filter_content_type

# 5. API query
# &fq=!relationship%3Achild added to ensure only parent pages are returned, i.e. not the content chunks used for embedding 
# (can't use fq=relationship%3Aparent because not all pages will have a value for relationship initially)
solrquery = 'select?fl=id,url,title,author,description,tags,page_type,page_last_modified,published_date,language,indexed_inlinks,indexed_outlinks&q={}&start={}&rows={}&wt=json&fq=domain%3A{}&fq=!relationship%3Achild&hl=on&hl.fl=content&hl.simple.pre={}&hl.simple.post={}'


# Solr update queries
# -------------------

# Delete queries, used in adminutils
solr_delete_query = "update?commit=true"
solr_delete_headers = {'Content-Type': 'text/xml'}
solr_delete_data = "<delete><query>domain:{}</query></delete>"
