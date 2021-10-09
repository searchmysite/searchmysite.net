from os import environ, path

SOLR_URL = 'http://search:8983/solr/content/'
DB_NAME = 'searchmysitedb'
DB_USER = 'postgres'
DB_HOST = 'db'

# POSTGRES_PASSWORD is normally set by docker from the .env file
# The .env file is normally in the main application root (searchmysite/src/)
# rather than FLASK_APP (searchmysite/src/web/content/dynamic/searchmysite)
# or PYTHONPATH (searchmysite/src/web/content/dynamic)
# However, if this is not set, e.g. because flask is being run outside docker, 
# and the .env file has not been loaded manually, load based on current location
# of either FLASK_APP or PYTHONPATH
DB_PASSWORD = environ.get('POSTGRES_PASSWORD') 
if not DB_PASSWORD:
    pythonpath = environ.get('PYTHONPATH')
    flask_app = environ.get('FLASK_APP')
    python_dir = path.abspath('')
    if pythonpath: python_dir = pythonpath
    elif flask_app: python_dir = flask_app
    env_file = path.join(python_dir, '../../../../.env')
    if not path.isfile(env_file): env_file = path.join(python_dir, '../../../.env')
    with open(env_file) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=')
                if key == 'POSTGRES_PASSWORD': DB_PASSWORD = value
