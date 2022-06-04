FROM solr:8.11.1-slim

# Copy the custom config files in. Note that in order to create the collection with this config, 
# we need to do a docker run with "solr-precreate content /opt/solr/server/solr/configsets/content"

ADD content /opt/solr/server/solr/configsets/content

# Dev docker-compose.yml has the following:
#    volumes:
#      - "../data/solrdata:/var/solr"
# No need to copy this in to the prod image though

