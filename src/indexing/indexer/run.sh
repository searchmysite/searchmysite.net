#!/bin/sh

S=120

if [ "$1" = "dev" ]
then
  S=60
  echo "Running in dev mode. Going to run search_my_site_scheduler.py more quickly"
elif [ "$1" = "test" ]
then
  echo "Running in test mode. Not going to run search_my_site_scheduler.py"
  while true
    do sleep $S
  done
fi

while true
  do python /usr/src/app/search_my_site_scheduler.py
  sleep $S
done

