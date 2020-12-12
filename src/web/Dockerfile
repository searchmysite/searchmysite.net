FROM httpd:2.4.43

# Working dir is /usr/local/apache2 so we'll end up with requirements.txt there, but that is outside the web root 
COPY requirements.txt ./

# Need git for the git+https:// in requirements.txt
RUN apt-get update && apt-get install -y git && apt-get install -y python3 && apt-get install -y python3-pip && pip3 install --no-cache-dir -r requirements.txt

# Need this to prevent "[wsgi:error] ... ModuleNotFoundError: No module named ..."
ENV PYTHONPATH /usr/local/apache2/htdocs/dynamic/

COPY conf/ /usr/local/apache2/conf/ 

ARG env

# docker-compose.yml (env=dev) and docker-compose.test.yml (env=test) have the following:
#    volumes:
#      - "./web/content:/usr/local/apache2/htdocs/:ro"
# For prod we need to copy the source files in to that location
COPY ./content/ /tmp/
RUN if [ "$env" = "prod" ] ; then cp -r /tmp/static/ /usr/local/apache2/htdocs/ ; cp -r /tmp/dynamic/ /usr/local/apache2/htdocs/ ; fi

