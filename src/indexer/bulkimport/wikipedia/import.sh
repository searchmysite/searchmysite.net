#!/bin/bash

echo "Step 1: Download"
cd cirrussearch
wget https://dumps.wikimedia.org/other/cirrussearch/20201214/enwiki-20201214-cirrussearch-content.json.gz
# A couple of hours to download, and approx 30Gb.

echo "Step 2: Uncompress"
gunzip enwiki-20201214-cirrussearch-content.json.gz
# Takes about 30 mins to uncompress, to approx 125Gb.
# Split the file into 500 line chunks

echo "Step 3"
mkdir unprocessed
cd unprocessed
split -a 6 -l 500 ../enwiki-20201214-cirrussearch-content.json enwiki-
# Takes about 47 mins.

