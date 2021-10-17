#!/bin/bash

# Search extracts available at https://dumps.wikimedia.org/other/cirrussearch/
# e.g. https://dumps.wikimedia.org/other/cirrussearch/current/enwiki-20210927-cirrussearch-content.json.gz
# Look like they're updated approx weekly. Also a significantly smaller test file at
# e.g. https://dumps.wikimedia.org/other/cirrussearch/current/testwiki-20210927-cirrussearch-content.json.gz
# Run on prod inside the docker container (so the python libs are available) with:
# docker exec -it src_indexing_1 /usr/src/app/bulkimport/wikipedia/import.sh >~/logs/bulkimport/wikipedia.log
# Note that the working directory inside the docker container is /usr/src/app/
# so we need to cd bulkimport/wikipedia before beginning

# Language code
LAN_CODE=en

FOLDER=cirrussearch/${LAN_CODE}
SOLR_URL=http://search:8983/solr/content/

cd bulkimport/wikipedia
mkdir -p $FOLDER


echo -ne "Step 1: Find the last successful wikipedia import, and see if there is a later one available"
LATEST_COMPLETED=`python -c 'import wikiutils; c = wikiutils.latest_complete(); print(c)'`
if [[ $LATEST_COMPLETED == "" ]]; then
    LATEST_COMPLETED=00000000
fi
echo -ne "\nLast completed $LATEST_COMPLETED"
LATEST_AVAILABLE=`python -c 'import wikiutils; a = wikiutils.latest_available(); print(a)'`
echo -ne "\nLast available $LATEST_AVAILABLE"
if [[ $LATEST_COMPLETED -ge $LATEST_AVAILABLE ]]; then
    echo -ne "\nThere isn't a later import available"
    exit 0
fi
URL_ROOT=https://dumps.wikimedia.org/other/cirrussearch/${LATEST_AVAILABLE}/
COMPRESSED_FILE=${LAN_CODE}wiki-${LATEST_AVAILABLE}-cirrussearch-content.json.gz


echo -ne "\nStep 2: Download, started at" `date`
python -c "import wikiutils; wikiutils.update_log(\"RUNNING\", \"Using export: ${LATEST_AVAILABLE}\")"
if [ -f "${FOLDER}/$COMPRESSED_FILE" ]; then
    echo -ne "${FOLDER}/$COMPRESSED_FILE exists. Skipping download."
else 
    wget -O ${FOLDER}/${COMPRESSED_FILE} ${URL_ROOT}${COMPRESSED_FILE}
fi


echo -ne "\nStep 3: Uncompress and split into smaller chunks, started at" `date`
gunzip -c ${FOLDER}/$COMPRESSED_FILE | split -a 6 -l 500 - ${FOLDER}/${LAN_CODE}wiki-
rm ${FOLDER}/$COMPRESSED_FILE # Delete downloaded file to save space


echo -ne "\n\nStep 4: Reformat, started at" `date`
for file in ${FOLDER}/*
do
    echo $file
    python reformatjson.py $file $LAN_CODE
done


echo -ne "\n\nStep 5: Load into Solr, started at" `date` "\n"
# Start by deleting existing Solr collection, for a clean index
# If allowing indexing multiple languages, delete query would be <delete><query>(domain:wikipedia.org)AND(language:${LAN_CODE})</query></delete>
curl ${SOLR_URL}update?commit=true -H "Content-Type: text/xml" --data-binary '<delete><query>domain:wikipedia.org</query></delete>'
for file in ${FOLDER}/*
do
    echo $file
    curl ${SOLR_URL}update?commit=true -H "Content-Type: application/json" --data-binary @$file
done
rm ${FOLDER}/*

echo -ne "\nCompleted at" `date` "\n"
python -c "import wikiutils; wikiutils.update_log(\"COMPLETE\", \"Using export: ${LATEST_AVAILABLE}\")"
