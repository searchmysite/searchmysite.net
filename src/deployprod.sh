#!/bin/bash
# Run on production to build and deploy
# Do not run on dev because you may lose work
# Move up 2 levels before running, i.e. after changing on dev execute the following on prod:
# cd
# rm -r searchmysite.net/
# git clone https://github.com/searchmysite/searchmysite.net.git
# cp ~/searchmysite.net/src/deployprod.sh ~/.
if [ "$USER" = "ubuntu" ] # To try and prevent accidental running on dev
then
  cd
  rm -r searchmysite.net/
  git clone https://github.com/searchmysite/searchmysite.net.git
  cp .env searchmysite.net/src/
  cd searchmysite.net/src/
  mv docker-compose.yml docker-compose.dev.yml
  mv docker-compose.prod.yml docker-compose.yml
  docker-compose build

  # If the indexer container is indexing sites when it is restarted it will leave the sites stuck in RUNNING status
  until grep -q "Checking for sites to index" <<< `docker logs --tail 1 src_indexer_1`
  do
    echo "Waiting for indexing job to finish"
    sleep 10
  done
  docker-compose up -d
	
  echo "If you have modified solr config you also need to:"
  echo "docker exec -it search_prod cp -r /opt/solr/server/solr/configsets/content/conf /var/solr/data/content/"
  echo "docker restart search_prod"
else
  echo "This needs to be run on production"
fi

