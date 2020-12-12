-- Migrate data from old to new schema
-- Instructions:
-- 1. After getting an ubuntu user readable copy of the latest backup in prod root, copy to local dev, e.g.
--    scp -i ~/.ssh/<prod-pem-file> ubuntu@<prod-server-name>:~/backup17.sql ~/projects/searchmysite/src/db/datamigration/
-- 2. Copy the public.tbldomains and public.tblfilters sections (no need for public.tblindexinglog)
-- 3. Copy over the COPY public.tbldomains line with the new COPY public.tblindexeddomains line to get the new table name and column names
--    and rename public.tblfilters to public.tblindexingfilters
-- 4. Copy the file to somewhere inside the container, e.g.
--    sudo cp ~/projects/searchmysite/src/db/datamigration/datamigration.sql  ~/projects/searchmysite/data/sqldata/
-- 5. Run inside container, i.e.
--    docker exec src_db_1 /bin/bash -c "psql -U postgres searchmysitedb < /var/lib/postgresql/data/datamigration.sql"
-- 6. Cleanup files:
--    sudo rm ~/projects/searchmysite/data/sqldata/datamigration.sql
--    rm ~/projects/searchmysite/src/db/datamigration/backup17.sql
-- 7. Run SQL to move pending submissions from tblindexeddomains to tblpendingdomains:
--    INSERT INTO tblPendingDomains(domain, home_page, owner_submitted, submission_method, date_domain_added, contact_email, validation_key, password) SELECT domain, home_page, owner_verified, validation_method, date_domain_added, contact_email, validation_key, password FROM tblIndexedDomains WHERE owner_verified = false
--    UPDATE tblPendingDomains SET owner_submitted = true, submission_method = 'DCV' WHERE owner_submitted = false
--    DELETE FROM tblIndexedDomains WHERE owner_verified = false
-- 8. Reindex everything and set indexing_frequency and indexing_page_limit to new default values:
--    UPDATE tblIndexedDomains SET  indexing_current_status = 'PENDING', indexing_frequency = '3.5 days', indexing_page_limit = 1000

COPY public.tblindexeddomains (domain, home_page, contact_email, date_domain_added, expire_date, api_enabled, owner_verified, validation_key, validation_method, validation_date, indexing_frequency, indexing_page_limit, indexing_current_status, indexing_status_last_updated, password, last_login) FROM stdin;
michael-lewis.com	https://michael-lewis.com/	michael@michael-lewis.com	2020-07-15 20:41:24.351+00	2021-07-30 16:22:42.250465+00	t	t	igaxp3GdObXAKvduvGRf941krMcHcIvVasCfB66srJ	DCV	2020-07-30 16:22:42.250465+00	4 days	400	COMPLETE	2020-09-16 16:41:07.11547+00	pbkdf2:sha256:150000$ai8I29cT$3a4c20aeb4abe5bec2693f2dc1493358ff379ef5a2b7c5826794cc9505e93273	\N
maxwelljoslyn.com	https://www.maxwelljoslyn.com/	maxwelljoslyn@gmail.com	2020-09-01 04:35:39.466361+00	2021-09-01 04:36:05.687683+00	t	t	\N	IndieAuth	2020-09-01 04:36:05.687683+00	4 days	400	COMPLETE	2020-09-13 05:07:35.437832+00	\N	\N
doubleloop.net	https://commonplace.doubleloop.net	neil@doubleloop.net	2020-07-25 09:51:45.486184+00	\N	t	f	SFmjoHDwhMJYNrpMoPkNpbHtBXtSzQ02zxPQCjuTSZ	\N	\N	4 days	400	PENDING	2020-07-25 09:51:45.486184+00	pbkdf2:sha256:150000$066F0J1L$d0f7eace4acbb1594586fef8bdbe9d6dbd29162f14f667d6c5701e3f0389d207	\N
q4.re	https://q4.re/	arne@q4.re	2020-09-01 06:13:44.425141+00	2021-09-01 06:13:48.22342+00	t	t	\N	IndieAuth	2020-09-01 06:13:48.22342+00	4 days	400	COMPLETE	2020-09-13 06:20:57.856516+00	\N	\N
degruchy.org	https://degruchy.org/	nathan@degruchy.org	2020-07-22 18:14:13.246171+00	2021-07-22 18:14:25.699872+00	t	t	\N	IndieAuth	2020-07-22 18:14:25.699872+00	4 days	400	COMPLETE	2020-09-13 14:46:43.499228+00	\N	\N
rich-text.net	https://www.rich-text.net/	rlbrown72@gmail.com	2020-08-25 13:17:32.981937+00	2021-08-25 13:18:37.250067+00	t	t	\N	IndieAuth	2020-08-25 13:18:37.250067+00	4 days	400	COMPLETE	2020-09-14 14:11:58.833838+00	\N	\N
susa.net	https://www.susa.net/wordpress/	kevin@susa.net	2020-08-31 22:36:07.535308+00	\N	t	f	322xzF0d00NcDtGUs5w8BxY1KAaa3ydMZWvuzcW0sf	\N	\N	4 days	400	PENDING	2020-08-31 22:36:07.535308+00	pbkdf2:sha256:150000$0wG0b9F5$a268144e2b2a95952ddca0082a30c547fae562d37b5ad1ed9c013f87c79cb3cb	\N
theadhocracy.co.uk	https://theadhocracy.co.uk/	murrayadcock@gmail.com	2020-07-17 21:42:54.309126+00	2021-07-17 21:43:02.485652+00	t	t	\N	IndieAuth	2020-07-17 21:43:02.485652+00	4 days	400	COMPLETE	2020-09-15 02:45:37.867926+00	\N	\N
aaronparecki.com	https://aaronparecki.com/	aaron@parecki.com	2020-07-17 20:47:15.651649+00	2021-07-17 20:47:22.017403+00	t	t	\N	IndieAuth	2020-07-17 20:47:22.017403+00	4 days	400	COMPLETE	2020-09-15 06:21:19.694263+00	\N	\N
jacky.wtf	https://v2.jacky.wtf	yo@jacky.wtf	2020-07-17 22:55:44.672432+00	2021-07-17 22:55:49.847782+00	t	t	\N	IndieAuth	2020-07-17 22:55:49.847782+00	4 days	400	COMPLETE	2020-09-15 06:21:19.694263+00	\N	\N
tantek.com	https://tantek.com/	donotmail@example.com	2020-07-24 20:50:58.537803+00	2021-07-24 20:51:21.851521+00	t	t	\N	IndieAuth	2020-07-24 20:51:21.851521+00	4 days	400	COMPLETE	2020-09-15 06:43:50.819542+00	\N	\N
notiz.blog	https://notiz.blog/	pfefferle@gmail.com	2020-07-25 09:44:05.144032+00	2021-07-25 09:44:15.736818+00	t	t	\N	IndieAuth	2020-07-25 09:44:15.736818+00	4 days	400	COMPLETE	2020-09-15 14:26:01.83218+00	\N	\N
snarfed.org	https://snarfed.org/	searchmysite@ryanb.org	2020-07-17 20:42:53.630757+00	2021-07-17 20:43:04.888913+00	t	t	\N	IndieAuth	2020-07-17 20:43:04.888913+00	4 days	400	COMPLETE	2020-09-16 08:36:32.820327+00	\N	\N
manton.org	https://www.manton.org/	manton@me.com	2020-07-17 21:54:47.882802+00	2021-07-17 21:54:58.859956+00	t	t	\N	IndieAuth	2020-07-17 21:54:58.859956+00	4 days	400	COMPLETE	2020-09-16 09:05:44.232109+00	\N	\N
jeremycherfas.net	https://www.jeremycherfas.net/	jcherfas@mac.com	2020-07-18 06:11:22.468856+00	2021-07-18 06:11:31.2928+00	t	t	\N	IndieAuth	2020-07-18 06:11:31.2928+00	4 days	400	COMPLETE	2020-09-16 09:31:58.108281+00	\N	\N
\.

COPY public.tblindexingfilters (domain, action, type, value) FROM stdin;
theadhocracy.co.uk	exclude	path	/search/\\?query=
aaronparecki.com	exclude	type	website
maxwelljoslyn.com	exclude	path	/page-bodies.txt
maxwelljoslyn.com	exclude	path	/tag
maxwelljoslyn.com	exclude	path	/all-tags
\.

