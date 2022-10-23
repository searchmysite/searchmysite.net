# searchmysite.net

This repository contains the complete codebase for [https://searchmysite.net/](https://searchmysite.net/), the independent open source search engine and search as a service, currently focussed on personal and independent websites (see [About searchmysite.net](https://searchmysite.net/pages/about/) for further details of searchmysite.net).

You can use this repository to:
- See exactly how searchmysite.net works, e.g. inspect the code for indexing, relevancy tuning, search queries etc.
- Help improve the searchmysite.net service, e.g. by reporting issues, suggesting improvements, or implementing fixes or enhancements. See [Contributing](CONTRIBUTING.md).
- Set up your own instance to provide a fully open and independent search for another part of the internet.


## Directory structure and docker-compose files

The application is split into 4 components, each deployed in its own Docker container:
- db - Postgres database (for managing site and indexing configuration)
- indexing - Scrapy web crawler and bulk import scripts (for indexing sites)
- search - Apache Solr search server (for the actual search index)
- web - Apache httpd with mod_wsgi web server, with static assets (including home page), and dynamic pages (including API)

The project directory structure is as follows:

    .
    ├── data                    # Data for Docker data volumes (not in git - to be set up locally)
    │   ├── solrdata            # Mounted to /var/solr/solrdata in Solr Docker
    │   ├── sqldata             # Mounted to /var/lib/postgresql/data in Postgres Docker
    ├── src                     # Source files
    │   ├── db                  # Database scripts
    │   ├── indexing            # Indexing code
    │   │   ├── bulkimport      # Bulk import scripts
    │   │   ├── common          # Indexing code shared between bulk import and spider
    │   │   ├── indexer         # Spidering code
    │   ├── search              # Search engine configuration
    │   ├── web                 # Files for deployment to web / app server
    │   │   ├── config          # Web server configuration
    │   │   ├── content/dynamic # Dynamic pages and API, for deployment to app server
    │   │   ├── content/static  # Static assets, for deployment to static web server
    ├── tests                   # Test scripts
    └── README.md               # This file

There are 3 docker-compose files, which are largely identical except:
- docker-compose.yml (for local dev) configures the web server and indexing to read from the source, so code changes don't require a rebuild.
- docker-compose.test.yml (for running test scripts) does not persist the database and search and doesn't run the scheduled indexing, so each test cycle can start with a clean and predictable environment.
- docker-compose.prod.yml (for production) persists the database and search, and copies in web server and indexing code.



## Setting up your development environment

### Prerequisites

Ensure [Docker Engine](https://docs.docker.com/engine/install/) and [Docker Compose](https://docs.docker.com/compose/install/) are installed.

Get the source code with e.g.
```
cd ~/projects/
git clone https://github.com/searchmysite/searchmysite.net.git
```

Create the data directories for the database and search index:
```
cd ~/projects/searchmysite.net/
mkdir -p data/solrdata
mkdir -p data/sqldata
sudo chown 8983:8983 data/solrdata
```

Create a ~/projects/searchmysite.net/src/.env file for the docker-compose.yml containing at least the following:
```
POSTGRES_PASSWORD=<password>
SECRET_KEY=<secretkey>
```
The POSTGRES_PASSWORD and SECRET_KEY can be any values you choose for local dev. Note that although these are the only values required for the basic application to work, there are other values which will need to be set up for additional functionality - see the "Additional environment variables" section below.

And finally, build the docker images:
```
cd ~/projects/searchmysite.net/src
docker-compose build
```


### Starting your development environment

With the prerequisites in place, you can start your development environment with:
```
cd ~/projects/searchmysite.net/src
docker-compose up -d
```
The website will be available at [http://localhost:8080/](http://localhost:8080/), and the Apache Solr admin interface at [http://localhost:8983/solr/#/](http://localhost:8983/solr/#/).


### Setting up an admin login

If you want to be able to Approve or Reject sites added as a Basic listing, you will need to set up one or more Admin users. Only verified site owners, i.e. ones with a Full listing and able to login, can be permissioned as Admin users. You can use the web interface to add your own site as Full listing via Add Site, or insert details directly into the database.

Once you have one or more verified site owners, you can permission them as Admins in the database, e.g.:
```
INSERT INTO tblPermissions (domain, role)
  VALUES ('michael-lewis.com', 'admin');
```


### Adding other websites

You can use Add Site to add a site or sites as a Basic listing via the web interface. You will need to login as an Admin user, click Review, and select Approve for them to be queued for indexing.

There are also bulk import scripts in src/db/bulkimport. checkdomains.py takes a list of domains or home pages as input, checks that they are valid sites, and that they aren't already in the list or the database, and generates a file for insertdomains.py to insert.


### Additional environment variables 

If you want to use functionality which sends emails (e.g. the Contact form) you will need to set the following values:
```
SMTP_SERVER=
SMTP_PORT=
SMTP_FROM_EMAIL=
SMTP_FROM_PASSWORD=
SMTP_TO_EMAIL=
```
If just testing, you can create a web based email account and use the SMTP details for that.

If you want to enable the payment mechanism for verified submissions, you will need to set:
```
ENABLE_PAYMENT=True
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_PRODUCT_ID=
STRIPE_ENDPOINT_SECRET=
```
If just testing, you can get a test account from [Stripe](https://stripe.com/).



## Making changes on local dev


### Web changes

The docker-compose.yml for dev configures the web server to read from the source, so changes can be made in the source and reloaded. The web server will typically have to be restarted to view changes: 

```
docker exec -it web_dev apachectl restart
```
For frequent changes it is better to use a Flask development environment outside of Docker.

To do this, given containers talk to each other internally via the "db", "indexing", "search" and "web" hostnames, you will need to set up local host entries for "search" and "db", i.e. in /etc/hosts:
```
127.0.0.1       search
127.0.0.1       db
```
After installing Flask and any dependencies locally (see requirements.txt), install the searchmysite package in editable mode (this just needs to be done once):
```
cd ~/projects/searchmysite.net/src/web/content/dynamic/
pip3 install -e .
```
then load environment variables and start Flask in development mode via:
```
set -a; source ~/projects/searchmysite.net/src/.env; set +a
export FLASK_ENV=development
export FLASK_APP=~/projects/searchmysite.net/src/web/content/dynamic/searchmysite
flask run
```
You local Flask website will be available at e.g. [http://localhost:5000/search/](http://localhost:5000/search/) (note that the home page, i.e. [http://localhost:5000/](http://localhost:5000/), isn't served dynamically so won't be available via Flask). Changes to the code will be reflected without a server restart, you will see debug log messages, and full stack traces will be more visible in case of errors.


### Indexing changes

As with the web container, the indexing container on dev is configured to read directly from the source, so changes just need to be saved.

You would typically trigger a reindex by running SQL like:
```
UPDATE tblDomains 
  SET  full_indexing_status = 'PENDING'
  WHERE domain = 'michael-lewis.com';	
```
and waiting for the next src/indexing/indexer/run.sh (up to 1 min on dev), or triggering it manually:
```
docker exec -it src_indexing_1 python /usr/src/app/search_my_site_scheduler.py 
```
There shouldn't be any issues with multiple schedulers running concurrently if you trigger it manually and the scheduled job then runs.

You can monitor the indexing logs via: 
```
docker logs -f src_indexing_1
```
and can change the LOG_LEVEL to DEBUG in src/indexing/indexer/settings.py.


### Search (Solr) changes

The dev Solr docker container copies in the config on build, so a `docker-compose build` is required for each config change.

Note that the `solr-precreate content /opt/solr/server/solr/configsets/content` doesn't actually load the new config after a `docker-compose build`, so the following steps are required to apply Solr config changes:
```
docker-compose build
docker-compose up -d
docker exec -it search_dev cp -r /opt/solr/server/solr/configsets/content/conf /var/solr/data/content/
docker restart search_dev
```

Depending on the changes, you may also need to delete some or all data in the index, e.g.
```
curl http://localhost:8983/solr/content/update?commit=true -H "Content-Type: text/xml" --data-binary '<delete><query>domain:michael-lewis.com</query></delete>'
```
and trigger reindexing as per above. Use `<query>*:*</query>` to delete all data in the index.

You can also delete and recreate the data/solrdata directory, then rebuild, for a fresh start.


### Database (Postgres) changes

You can connect to the database via:
```
  "host": "127.0.0.1",
  "user": "postgres",
  "port": 5432,
  "ssl": false,
  "database": "searchmysitedb",
  "password": <password-from-dotenv-file>
```
Schema changes should be applied to the src/db/sql/init* files so if you delete and recreate the data/sqldata directory the latest schema is applied.


## Relevancy tuning

For basic experimentation with relevancy tuning, you can manually add a few sites, and experiment with those. Remember to ensure there are links between these sites, because indexed_inlink_domains_count is an important factor in the scoring. Remember also that indexed_inlink* values may require sites to be indexed twice to be correctly set - the indexing process sets indexed_inlink* values from the indexed_outlink* values, so needs a first pass to ensure all sites to have indexed_outlink* values set.

However, for serious relevancy tuning, it is better to use a restore of the production Solr collection. If you are interested in doing this, let me know and I'll make an up-to-date one available.

Note that if you add new fields to the Solr schema which are to be used in the relevancy scoring, it is better to wait until all the sites have had these fields added before deploying the new relevancy scoring changes. There are two ways of doing this: force a reindex of all sites, or wait until all sites are naturally reindexed. It is easier and safer to wait for the natural reindex. The force reindexed reindex of everything is likely to take over 24 hours given reindexing happens in batches of 20 and some sites take over 1 hour to reindex, while a natural reindexing will take 3.5 days to ensure all the verified sites are reindexed (28 days for unverified sites).


## Testing

The tests are run with pytest on a local Flask instance, so you will need to install pytest and set up a local Flask instance as per the "Making changes on local dev" / "Web changes" section above. If you have ENABLE_PAYMENT=True, you will also need to setup Selenium and WebDriver, because the Stripe integration involves buttons which execute JavaScript, e.g.:
```
pip3 install selenium
pip3 install chromedriver-py
```

There are two test scripts:
- `clean_test_env.sh` - shuts down any dev docker instances, rebuilds and starts the clean test docker instances.
- `run_tests.sh` - sets up the environment variables, runs the pytest scripts and the indexing.

The pytest scripts:
- submit and approve a Basic listing
- submit a Full listing site, including making a test payment to the Stripe account specified with the STRIPE_* variables if ENABLE_PAYMENT=True
- search the newly indexed sites
- remove the test sites

To run:
```
cd ~/projects/searchmysite.net/tests
./clean_test_env.sh
./run_tests.sh
```

The indexing step will take minute or two, given it is performing indexing of real sites, and if ENABLE_PAYMENT=True you'll see a browser pop up which takes a few seconds to open and close.

If the tests succeed, it will leave the environment in the same state it was at the start, i.e. it cleans up after itself, so you don't need to run `clean_test_env.sh` before `run_tests.sh` again. If however, the tests fail, you will need to rerun `clean_test_env.sh`. For the same reason, if you accidentally run `run_tests.sh` against the dev rather than test env, e.g. because you didn't run `clean_test_env.sh` first, then if the tests succeed then the environment will be fine. It is better to use the test docker environment though because this provides a known clean starting point, and ensures the scheduled reindexing doesn't interfere with the indexing in the testing.


