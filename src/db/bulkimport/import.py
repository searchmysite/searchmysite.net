#!/usr/bin/env python3
import urllib.request
from urllib.error import URLError, HTTPError
from http.client import InvalidURL
import tldextract
import json
import sys
import psycopg2
import psycopg2.extras
import os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(SCRIPT_DIR))
from common.utils import get_args, extract_domain, select_all_domains, insert_domain, approve_domain

# Instructions:
#
# Step 1: create the input file at import.txt. It must be a text file with a list of domains  
# (e.g. michael-lewis.com) or home page links (e.g. https://michael-lewis.com/) each on a new line.
#
# Step 2: run `./import.py` or `./import.py --env prod`
# Make sure that you have your python env set up. If running against dev, make sure your local dev 
# is up and running. import.py will do a bunch of checks, e.g. to make sure the site is responding, 
# that it isn't already in the database, and so on.
#
# Step 3: run `./import.py --update` or `./import.py --env prod --update`
# To actually import the sites. Note the hardcoded values used during site insert.


input_file = "import.txt"
if not os.path.exists(input_file):
    exit("You need to provide an input file at {}. This ".format(input_file))

args = get_args()

# Values used during site insert
moderator_approved = True
moderator = 'michael-lewis.com'
category = "personal-website"
tier = 1

def check_domains(all_domains):
    domains = []
    headers = {'Accept': 'text/html', 'User-Agent': 'Python'} # Some sites give a 403 Forbidden if they don't get headers
    f = open(input_file, 'r')
    lines = f.readlines()
    for line in lines:
        line = line.strip()
        if line != "" and not line.startswith("#"):
            print("\nChecking {}".format(line))
            result = {}

            # Step 1: Get input domain and home_page
            if line.startswith("http"):
                domain = extract_domain(line)
                home_page = line
            else:
                domain = line.lower()
                home_page = "http://" + domain + "/"

            # Step 2: Get response
            try:
                req = urllib.request.Request(home_page, method="HEAD", headers=headers)
                resp = urllib.request.urlopen(req)
                home_page = resp.url # Going to get the home page from the response in case there have been redirects
                domain = extract_domain(home_page)
                response_code = resp.getcode()
                if response_code == 200:
                    valid = True
                    message = "Success"
                else:
                    valid = False
                    message = "Unknown response code {}".format(response_code)
            except HTTPError as err:
                if err.reason == "Permanent Redirect": # Some sites return a 308 Permanent Redirect for an http request to be redirected to https but don't provide the Location header so this throws an HTTPError
                    try:
                        home_page = "https://" + domain + "/"
                        req = urllib.request.Request(home_page, method="HEAD", headers=headers)
                        resp = urllib.request.urlopen(req)
                        domain = extract_domain(home_page)
                        response_code = resp.getcode()
                        if response_code == 200:
                            valid = True
                            message = "Success"
                    except:
                            valid = False
                            response_code = "-"
                            message = "Error {}".format(response_code)
                else:
                    valid = False
                    response_code = err.code
                    message = "HTTPError ({})".format(err.reason)
            except InvalidURL as err:
                valid = False
                response_code = resp.getcode()
                message = "InvalidURL ({})".format(err)
            except URLError as err:
                valid = False
                response_code = resp.getcode()
                message = "URLError ({})".format(err.reason)
            except:
                valid = False
                response_code = resp.getcode()
                message = "Other error ({})".format(sys.exc_info())

            # Step 3: See if it is a duplicate entry in the input file
            if valid:
                already_in_list = False
                for d in domains:
                    if d['domain'] == domain:
                        already_in_list = True

            # Step 4: See if it is already in the database
            if valid and not already_in_list:
                already_in_database = False
                if domain in all_domains:
                    already_in_database = True

            if not valid:
                print("Not valid. Error message: {}.".format(message))
            elif already_in_list:
                print("Already in list.")
            elif already_in_database:
                print("Already in database.")
            else:
                print("Good.")
                result['domain'] = domain
                result['home_page'] = home_page
                domains.append(result)

    f.close()
    return domains

all_domains = select_all_domains()
domains_to_import = check_domains(all_domains)

print("\nList of domains to import: {}".format(domains_to_import))

if args.update:
    for domain in domains_to_import:
        print("\nImporting {}".format(domain['domain']))
        insert_domain(domain['domain'], domain['home_page'], category, tier)
        if moderator_approved:
            approve_domain(domain['domain'], moderator)
