#!/bin/bash
cd ~/projects/searchmysite.net/src
docker-compose down
docker-compose -f docker-compose.test.yml build
# Note: if you need a rebuild, you may need to use the following instead, but this is not enabled by default because it takes several minutes 
#docker-compose -f docker-compose.test.yml build --no-cache
docker-compose -f docker-compose.test.yml up -d
sleep 10
cd ~/projects/searchmysite.net/tests

