import sys
import os

# Change the sys path so we can import utilities common to both the src/indexer/bulkimport and src/indexer/indexer 
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from common import config
from common import utils

# This file is just a wrapper for some utils, to allow a shell script to call them more easily

domain = "wikipedia.org"
dump_location = "https://dumps.wikimedia.org/other/cirrussearch/"

def update_log(status, message):
    utils.update_indexing_log(domain, status, message)

def latest_complete():
    latest_complete = utils.get_latest_completed_wikipedia_import(domain)
    return latest_complete

def latest_available():
    latest_available = utils.get_latest_available_wikipedia_export(dump_location)
    return latest_available


