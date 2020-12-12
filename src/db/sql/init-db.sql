CREATE DATABASE searchmysitedb;

\c searchmysitedb

-- /usr/local/bin/docker-entrypoint.sh runs *.sql, *.sql.gz, or *.sh in /docker-entrypoint-initdb.d/
-- so (a) specify full path as it won't be found in /usr/local/bin/, and (b) need to change extension so it isn't run twice
\i /docker-entrypoint-initdb.d/init-tables.inc

