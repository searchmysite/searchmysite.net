from os import environ, path

SOLR_URL = 'http://search:8983/solr/content/'
DB_NAME = 'searchmysitedb'
DB_USER = 'postgres'
DB_HOST = 'db'

# Within a docker container, the POSTGRES_PASSWORD will be available 
# in an environment variable set by docker-compose.yml from the .env. 
# The code to try to load it from a .env file is only if you're running 
# the Python code outside of the docker container, most likely on dev 
# during development. In fact the .env file isn't even copied in to the 
# docker container given the Dockerfile in effect does a 
# cp -r src/indexing/* /usr/src/app
# and the .env file is in src/ rather than src/indexing.
DB_PASSWORD = environ.get('POSTGRES_PASSWORD') 
if not DB_PASSWORD:
    pythonpath = environ.get('PYTHONPATH')
    python_dir = path.abspath('')
    if pythonpath: python_dir = pythonpath
    env_file = path.join(python_dir, '.env')
    if not path.isfile(env_file): env_file = path.join(python_dir, '../.env')
    if not path.isfile(env_file): env_file = path.join(python_dir, '../../.env')
    if not path.isfile(env_file): env_file = path.join(python_dir, '../../../.env')
    with open(env_file) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=')
                if key == 'POSTGRES_PASSWORD': DB_PASSWORD = value
