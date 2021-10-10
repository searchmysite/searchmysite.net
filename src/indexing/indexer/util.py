from dateutil.parser import parse, ParserError
from scrapy.utils.log import configure_logging
from scrapy.utils.project import get_project_settings
import logging
from urllib.parse import urlsplit
import tldextract

# Solr's DatePointField (pdate) requires UTC time in the DateTimeFormatter.ISO_INSTANT format, i.e.
# YYYY-MM-DDThh:mm:ssZ
# This converts strings to that format.
# Some sites have date strings which throw a ParserError, 
# e.g. <meta property="article:published_time" content="2019-02-21_1220"> throws a 
# dateutil.parser._parser.ParserError: Unknown string format: 2019-02-21_1220
# So catch those
def convert_string_to_utc_date(date_string):
    date_utc = None
    if date_string != '' and date_string != None:
        try:
            date_string = parse(date_string) # convert string of unknown format to datetime object
            date_utc = date_string.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ParserError:
            configure_logging(get_project_settings())
            logger = logging.getLogger()
            logger.info('Unable to parse date string {}'.format(date_string))
    return date_utc

# Convert Python datetime objects to Solr's format
def convert_datetime_to_utc_date(date_datetime):
    date_utc = None
    if date_datetime != '' and date_datetime != None:
        date_utc = date_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
    return date_utc

# Convert BeautifulSoup html object to relatively clean plain text
def get_text(html):
    text = html.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = ' \n '.join(chunk for chunk in chunks if chunk)
    if text == "": text = None
    return text

# This is a variant of ../../web/content/dynamic/admin/util.py which takes domains_allowing_subdomains as an input parameter -
# don't want a database lookup every time this is called in this context
def extract_domain(url, domains_allowing_subdomains):
    # Get the domain from the URL
    tld = tldextract.extract(url) # returns [subdomain, domain, suffix]
    domain = '.'.join(tld[1:]) if tld[2] != '' else tld[1] # if suffix empty, e.g. localhost, just use domain
    domain = domain.lower() # lowercase the domain to help prevent duplicates
    # Add subdomain if in domains_allowing_subdomains
    if domain in domains_allowing_subdomains: # special domains where a site can be on a subdomain
        if tld[0] and tld[0] != "":
            domain = tld[0] + "." + domain
    return domain

# Process the URL to remove the query string
# No longer in use
def remove_query_string(url):
    url_without_query_string = urlsplit(url)._replace(query=None).geturl()
    return url_without_query_string
