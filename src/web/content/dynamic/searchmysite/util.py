from flask import current_app
import tldextract
import domcheck
import random, string
import psycopg2
import psycopg2.extras
from os import environ
from urllib.request import urlopen, Request
import smtplib, ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from searchmysite.db import get_db
import config

smtp_server = environ.get('SMTP_SERVER')
smtp_port = environ.get('SMTP_PORT')
smtp_from_email = environ.get('SMTP_FROM_EMAIL')
smtp_from_password = environ.get('SMTP_FROM_PASSWORD')
smtp_to_email = environ.get('SMTP_TO_EMAIL')

domains_allowing_subdomains_sql = "SELECT setting_value FROM tblSettings WHERE setting_name = 'domain_allowing_subdomains';"

deletesql = "DELETE FROM tblIndexingFilters WHERE domain = (%s); DELETE FROM tblPermissions WHERE domain = (%s); DELETE FROM tblDomains WHERE domain = (%s);" # tblIndexingFilters and tblPermissions have a foreign key so delete first
solr_delete_query = "update?commit=true"
solr_delete_headers = {'Content-Type': 'text/xml'}
solr_delete_data = "<delete><query>domain:{}</query></delete>"

# This returns a domain when given a URL, e.g. returns michael-lewis.com for https://www.michael-lewis.com/about/
# This is a crucial piece of code because it generates the primary key for each account in the system, 
# i.e. the key is domain which is generated from the user entered URL.
# There is a special case for some domains to allow subdomains. This is to allow more than one account from that domain,
# e.g. http://user1.github.io/ will return user1.github.io rather than github.io so the system will support a
# later http://user2.github.io/
def extract_domain(url):
    # Get the domain from the URL
    if not url: url =""
    tld = tldextract.extract(url) # returns [subdomain, domain, suffix]
    domain = '.'.join(tld[1:]) if tld[2] != '' else tld[1] # if suffix empty, e.g. localhost, just use domain
    domain = domain.lower() # lowercase the domain to help prevent duplicates
    # Look up list of domains which allow subdomains from database
    domains_allowing_subdomains = []
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(domains_allowing_subdomains_sql)
    results = cursor.fetchall()
    for result in results:
        domains_allowing_subdomains.append(result['setting_value'])
    # Add subdomain if in domains_allowing_subdomains
    if domain in domains_allowing_subdomains: # special domains where a site can be on a subdomain
        if tld[0] and tld[0] != "":
            domain = tld[0] + "." + domain
    return domain


# Get the actual host URL, for use in links which need to contain the servername and protocol
# This will be 'http://127.0.0.1:5000/' if run in Flask and 'http://127.0.0.1:8080/' if run in Apache httpd + mod_wsgi
# If run behind a reverse proxy, production will also be 'http://127.0.0.1:8080/', 
# but the proxy must be explicitly configured to set the original host in X-Forwarded-Host so the proper value can be returned
def get_host(url, headers):
    current_app.logger.debug('request.headers: {}'.format(headers))
    forwarded_host = headers.get('X-Forwarded-Host')
    if url.startswith('http://127.0.0.1:8080/') and forwarded_host:
        url = url.replace('http://127.0.0.1:8080/', 'https://' + forwarded_host + '/', 1)
    return(url)

def generate_validation_key(no_of_digits):
    validation_key = ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(no_of_digits))
    return validation_key

def check_for_validation_key(domain, prefix, validation_key):
    validation_method = ""
    if domcheck.check(domain, prefix, validation_key): validation_method = "DCV"
    return validation_method

def delete_domain(domain):
    # Delete from Solr
    solrurl = config.SOLR_URL
    solrquery = solrurl + solr_delete_query
    data = solr_delete_data.format(domain)
    req = Request(solrquery, data.encode("utf8"), solr_delete_headers)
    response = urlopen(req)
    results = response.read()
    # Delete from database
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(deletesql, (domain, domain, domain,))
    conn.commit()

# reply_to_email and to_email optional.
# If reply_to_email None no Reply-To header set, and if to_email None then smtp_to_email env variable is used
def send_email(reply_to_email, to_email, subject, text): 
    success = True
    if not to_email:
        to_email = smtp_to_email
    context = ssl.create_default_context()
    try:
        message = MIMEMultipart()
        message["From"] = smtp_from_email
        message["To"] = to_email
        if reply_to_email:
            message['Reply-To'] = reply_to_email
        message["Subject"] = subject
        message.attach(MIMEText(text, "plain"))
        server = smtplib.SMTP(smtp_server, smtp_port)
        #server.set_debuglevel(1)
        server.starttls(context=context) # Secure the connection
        server.login(smtp_from_email, smtp_from_password)
        server.sendmail(smtp_from_email, smtp_to_email, message.as_string())
    except Exception as e:
        success = False
        current_app.logger.error('Error sending email: {}'.format(e))
    finally:
        server.quit() 
    return success
