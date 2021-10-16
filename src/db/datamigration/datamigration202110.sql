-- Release process
-- Check no indexing jobs are running via:
-- docker logs -f src_indexing_1
-- If none running, stop the indexing, so the indexing job won't make any database updates:
-- docker stop src_indexing_1
-- Create the new tables, and copy the data in, as per below
-- If there's an issue at this point it is easy to rollback - just delete the new tables
-- If all okay, then do the new code deployment to start using the new tables
-- Delete the old tables after a few days

-- Create a new tblDomains table

CREATE TABLE tblDomains (
  domain TEXT PRIMARY KEY,
  home_page TEXT NOT NULL,
  contact_email TEXT,
  site_category TEXT,
  date_domain_added TIMESTAMPTZ,
  expire_date TIMESTAMPTZ,
  api_enabled Boolean,
  owner_verified Boolean,
  validation_key TEXT,
  validation_method TEXT,
  validation_date TIMESTAMPTZ,
  moderator_approved Boolean, -- NEW
  moderator_action_date TIMESTAMPTZ, -- NEW
  moderator_action_reason TEXT, -- NEW
  moderator_action_user TEXT, -- NEW
  indexing_enabled Boolean, -- NEW
  indexing_disabled_date TIMESTAMPTZ, -- NEW
  indexing_disabled_reason TEXT, -- NEW
  indexing_type TEXT,
  indexing_frequency INTERVAL,
  indexing_page_limit SMALLINT,
  indexing_current_status TEXT,
  indexing_status_last_updated TIMESTAMPTZ,
  password TEXT,
  last_login TIMESTAMPTZ,
  forgotten_password_key TEXT,
  forgotten_password_key_expiry TIMESTAMPTZ
);

-- Copy everything in from tblIndexedDomains
-- setting the new fields to 
-- moderator_approved=TRUE, indexing_enabled=TRUE, moderator_action_date=validation_date-'1 year', moderator_action_user='michael-lewis.com'

INSERT into tblDomains (
  domain,
  home_page,
  contact_email,
  site_category,
  date_domain_added,
  expire_date,
  api_enabled,
  owner_verified,
  validation_key,
  validation_method,
  validation_date,
  moderator_approved, -- NOTE new field
  moderator_action_date, -- NOTE new field
  moderator_action_user, -- NOTE new field
  indexing_enabled, -- NOTE new field
  indexing_type,
  indexing_frequency,
  indexing_page_limit,
  indexing_current_status,
  indexing_status_last_updated,
  password,
  last_login,
  forgotten_password_key,
  forgotten_password_key_expiry
) SELECT
  domain,
  home_page,
  contact_email,
  site_category,
  date_domain_added,
  expire_date,
  api_enabled,
  owner_verified,
  validation_key,
  validation_method,
  validation_date,
  TRUE, -- NOTE new field value
  null, -- NOTE new field value
  'michael-lewis.com', -- NOTE new field value
  TRUE, -- NOTE new field value
  indexing_type,
  indexing_frequency,
  indexing_page_limit,
  indexing_current_status,
  indexing_status_last_updated,
  password,
  last_login,
  forgotten_password_key,
  forgotten_password_key_expiry
FROM tblIndexedDomains;

-- Now copy all the data from tblPendingDomains
-- setting the new fields to 
-- moderator_approved=NULL, indexing_enabled=FALSE

INSERT into tblDomains (
  domain,
  home_page,
  contact_email,
  site_category,
  date_domain_added,
  -- owner_submitted,
  owner_verified,
  validation_method, -- NOTE different field name
  validation_key,
  moderator_approved, -- NOTE new field
  indexing_enabled, -- NOTE new field
  password
) SELECT
  domain,
  home_page,
  contact_email,
  site_category,
  date_domain_added,
  -- owner_submitted,
  owner_verified,
  submission_method,
  validation_key,
  NULL, -- NOTE new field value
  FALSE, -- NOTE new field value
  password
FROM tblPendingDomains;

-- And copy all the data from tblExcludeDomains
-- setting the new fields to 
-- moderator_approved=FALSE, indexing_enabled=FALSE, moderator_action_user='michael-lewis.com'

INSERT into tblDomains (
  domain,
  home_page,
  moderator_approved, -- NOTE new field
  moderator_action_date,
  moderator_action_reason,
  moderator_action_user, -- NOTE new field
  indexing_enabled -- NOTE new field
) SELECT
  domain,
  home_page,
  FALSE,
  exclusion_date,
  reason,
  'michael-lewis.com',
  FALSE
FROM tblExcludeDomains;

-- Change foreign keys on tblIndexingFilters and tblPermissions
-- this shows as syntax error in my editor, but runs

ALTER TABLE tblIndexingFilters 
  DROP CONSTRAINT domain_fkey,
  ADD CONSTRAINT domain_fkey FOREIGN KEY (domain)
    REFERENCES tblDomains (domain) MATCH SIMPLE
    ON UPDATE NO ACTION ON DELETE NO ACTION;

ALTER table tblPermissions 
  DROP CONSTRAINT domain_fkey,
  ADD CONSTRAINT domain_fkey FOREIGN KEY (domain)
    REFERENCES tblDomains (domain) MATCH SIMPLE
    ON UPDATE NO ACTION ON DELETE NO ACTION;

-- At this point we should be able to delete the old tables, i.e.
-- DROP TABLE tblIndexedDomains, tblPendingDomains, tblExcludeDomains;
-- But keeping for now for reference just in case there is an issue

