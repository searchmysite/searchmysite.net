FROM httpd:2.4.50
# httpd:2.4.51 to httpd:2.4.54 will install Python 3.9.2 rather than 3.7.3, which causes psycopg2 to intermittently error:
# ImportError: cannot import name 'encodings' from 'psycopg2._psycopg'

# Working dir is /usr/local/apache2 so we'll end up with requirements.txt there, but that is outside the web root 
COPY requirements.txt ./

# Need git for the git+https:// in requirements.txt
# Need libpq-dev and python3-dev for the psycopg2 in requirements.txt
# Need apache2-dev libapr1 libapr1-dev for the mod-wsgi in requirements.txt
# Need build-essential, python-dev, libffi-dev, libssl-dev, zlib1g-dev, libbz2-dev, and liblzma-dev for the cryptography>=35.0 in requirements.txt
RUN apt-get update && apt-get install -y git && apt-get install -y python3 && apt-get install -y python3-pip && python3 -m pip install --no-cache-dir --upgrade pip && apt-get install -y libpq-dev python3-dev apache2-dev libapr1 libapr1-dev build-essential libffi-dev libssl-dev zlib1g-dev libbz2-dev liblzma-dev && pip3 install --no-cache-dir -r requirements.txt

# Need this to prevent "[wsgi:error] ... ModuleNotFoundError: No module named ..."
ENV PYTHONPATH /usr/local/apache2/htdocs/dynamic/

COPY conf/ /usr/local/apache2/conf/ 

ARG env

# docker-compose.yml (env=dev) and docker-compose.test.yml (env=test) have the following:
#    volumes:
#      - "./web/content:/usr/local/apache2/htdocs/:ro"
# For prod we need to copy the source files in to that location
COPY ./content/ /tmp/
RUN if [ "$env" = "prod" ] ; then cp -r /tmp/static/ /usr/local/apache2/htdocs/ ; cp -r /tmp/dynamic/ /usr/local/apache2/htdocs/ ; chown -R www-data:www-data /usr/local/apache2/htdocs ; fi

