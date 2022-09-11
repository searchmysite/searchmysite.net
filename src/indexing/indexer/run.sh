#!/bin/sh

S=120

if [ "$1" = "dev" ]
then
  S=60
  echo "Running in dev mode. Going to run search_my_site_scheduler.py every 60s rather than every 120s."
elif [ "$1" = "test" ]
then
  echo "Running in test mode. Not going to run search_my_site_scheduler.py"
  while true
    do sleep $S
  done
fi

# Give the database etc. time to start
sleep $S

while true
  do python /usr/src/app/search_my_site_scheduler.py
  sleep $S
done

