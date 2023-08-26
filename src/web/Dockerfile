FROM httpd:2.4.57
# httpd:2.4.50 is Python 3.7.3, httpd:2.4.51 to httpd:2.4.54 are Python 3.9.2, and httpd:2.4.57 is Python 3.11.2

# Working dir is /usr/local/apache2 so we'll end up with requirements.txt there, but that is outside the web root 
COPY requirements.txt ./

# Need apache2-dev for the mod-wsgi in requirements.txt
# Need libpq-dev and python3-dev for the psycopg2 in requirements.txt
# Need git for the git+https:// in requirements.txt
RUN apt-get update && apt-get install -y apache2-dev libpq-dev git && apt-get install -y python3 python3-pip python3-dev

# Install pip packages, with --break-system-packages to avoid the "error: externally-managed-environment" as per PEP 668 
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Need this to prevent "[wsgi:error] ... ModuleNotFoundError: No module named ..."
ENV PYTHONPATH /usr/local/apache2/htdocs/dynamic/

# By default the model is cached to /root/.cache/torch/sentence_transformers/sentence-transformers_all-MiniLM-L6-v2/
# but /root is drwx------ and root:root and Flask/WSGI apps in the Apache httpd docker container run as daemon (uid 1)
# so create the /root/.cache/ and grant write access to daemon:daemon (1:1)
RUN chmod 755 /root ; mkdir -p /root/.cache/ ; chown -R 1:1 /root/.cache/

COPY conf/ /usr/local/apache2/conf/ 

ARG env

# docker-compose.yml (env=dev) and docker-compose.test.yml (env=test) have the following:
#    volumes:
#      - "./web/content:/usr/local/apache2/htdocs/:ro"
# For prod we need to copy the source files in to that location
COPY ./content/ /tmp/
RUN if [ "$env" = "prod" ] ; then cp -r /tmp/static/ /usr/local/apache2/htdocs/ ; cp -r /tmp/dynamic/ /usr/local/apache2/htdocs/ ; chown -R www-data:www-data /usr/local/apache2/htdocs ; fi

