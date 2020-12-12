#!/bin/bash
cd ~/projects/searchmysite/src
docker-compose down
docker-compose -f docker-compose.test.yml build
docker-compose -f docker-compose.test.yml up -d
cd ~/projects/searchmysite/tests


