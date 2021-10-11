#!/bin/bash

export PYTHONPATH=~/projects/searchmysite.net/src/web/content/dynamic/
export FLASK_APP=~/projects/searchmysite.net/src/web/content/dynamic/searchmysite
set -a; source ~/projects/searchmysite.net/src/.env; set +a

echo "Unit test"
pytest web/unit/test_adminutil.py

echo "PART 1 of 5: Submitting test site via Quick Add"
pytest -v web/integration/test_1_quickadd.py

echo "PART 2 of 5: Submitting test site via Verified Add (DCV)"
pytest -v web/integration/test_2_verifiedadddcv.py

echo "PART 3 of 5: Indexing test sites (please wait, this may take some time)"
docker exec -it src_indexing_1 python /usr/src/app/search_my_site_scheduler.py >/dev/null

echo "PART 4 of 5: Searching test site"
pytest -v web/integration/test_4_search.py

echo "PART 5 of 5: Removing test site"
pytest -v web/integration/test_5_remove.py

