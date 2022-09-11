-- Release process:
-- 1. Check there are no submissions pending review, and that the system is in a consistent state 
--    (i.e. no domain in the database but not search and vice versa) via consistencycheck.py.
-- 2. Check no indexing jobs are running via:
--       docker logs -f src_indexing_1
--    If none running, stop the indexing, so the indexing job won't make any database updates:
--       docker stop src_indexing_1
-- 3. Stop the web site to prevent the chance of any data updates (don't normally do this, but this is an unusual release):
--       docker stop web_prod
-- 4. Move the existing tblDomains, tblIndexingFilters and tblPermissions tables as per below. Note that 
--    tblIndexingLog and tblSettings can be left as is given they have no foreign key constraints.
--    Note also that moving tblDomains will update the foreign key constraints in tblIndexingFilters and tblPermissions.

ALTER TABLE IF EXISTS tblDomains
RENAME TO archivetblDomains;

ALTER TABLE IF EXISTS tblIndexingFilters
RENAME TO backuptblIndexingFilters;

ALTER TABLE IF EXISTS tblPermissions
RENAME TO backuptblPermissions;

-- 5. Create the updated tblDomains, new tblTiers, new tblListingStatus, new tblSubscriptions, new tblValidations,
--    updated tblIndexingFilters, and updated tblPermissions from init-tables.inc. As per step 3, no need to update 
--    tblIndexingLog and tblSettings.
-- 6. Insert the tblTiers static data from init-tables.inc.
-- 7. Copy the existing data from archivetblDomains into the updated tblDomains and new 
--    tblListingStatus, tblSubscriptions and tblValidations as per below.
--    Note that if there's an issue at this point it is easy to rollback - just delete the new tables and move the old tables back.
--    Note also that this only copies in the currently indexed domains - it makes no attempt to copy in domains which have been 
--    rejected, or domains which have started the verified add process and not completed the process, or domains where indexing has been
--    disabled due to indexing failing twice in a row.

INSERT into tblDomains (
  domain,
  home_page,
  category,
  domain_first_submitted,
  email,
  include_in_public_search,
  password,
  moderator_approved,
  moderator_action_reason,
  moderator_action_changed,
  moderator,
  full_reindex_frequency,
  indexing_page_limit,
  api_enabled,
  indexing_enabled,
  indexing_disabled_reason,
  indexing_disabled_changed,
  indexing_type,
  full_indexing_status,
  full_indexing_status_changed,
  last_login,
  forgotten_password_key,
  forgotten_password_key_expiry
) SELECT
  domain,
  home_page,
  site_category,
  date_domain_added,
  contact_email,
  include_in_public_search,
  password,
  moderator_approved,
  moderator_action_reason,
  moderator_action_date,
  moderator_action_user,
  indexing_frequency,
  indexing_page_limit,
  api_enabled,
  indexing_enabled,
  indexing_disabled_reason,
  indexing_disabled_date,
  indexing_type,
  indexing_current_status,
  indexing_status_last_updated,
  last_login,
  forgotten_password_key,
  forgotten_password_key_expiry
FROM archivetblDomains
WHERE moderator_approved = TRUE AND indexing_enabled = TRUE;

-- set login_type for Full listing sites (either INDIEAUTH or PASSWORD)
-- Note that 1 site verified with IndieAuth but I think now logs in with a password so we can't use the validation_method

UPDATE tblDomains SET login_type = 'PASSWORD' WHERE password IS NOT NULL AND api_enabled = TRUE;
UPDATE tblDomains SET login_type = 'INDIEAUTH' WHERE password IS NULL AND api_enabled = TRUE;

-- set on_demand_reindexing to True for Full listing sites and False for Basic listing sites

UPDATE tblDomains SET on_demand_reindexing = TRUE WHERE api_enabled = TRUE;
UPDATE tblDomains SET on_demand_reindexing = FALSE WHERE api_enabled = FALSE;

-- add details to tblListingStatus and tblSubscriptions
-- Going to default everything to tier 1 for the insert because tier is a required field, then change the tier 3 domains to tier 3

INSERT INTO tblListingStatus (
  domain,
  tier,
  status,
  pending_state_changed,
  listing_start,
  listing_end
) SELECT 
  domain,
  1,
  'ACTIVE' as status,
  expire_date - INTERVAL '1 year' AS pending_state_changed,
  expire_date - INTERVAL '1 year' AS listing_start,
  expire_date AS listing_end
FROM archivetblDomains
WHERE moderator_approved = TRUE AND indexing_enabled = TRUE;
UPDATE tblListingStatus SET tier = 3 WHERE domain in (SELECT domain FROM tblDomains WHERE api_enabled = TRUE);

INSERT INTO tblSubscriptions (
  domain,
  tier,
  subscribed,
  subscription_start,
  subscription_end
) SELECT 
  domain,
  tier,
  listing_start AS subscribed,
  listing_start AS subscription_start,
  listing_end AS subscription_end
FROM tblListingStatus
WHERE tier = 3;

-- set validation_key/method/date in tblValidations

INSERT INTO tblValidations (
  domain,
  validation_date,
  validation_method,
  validation_success,
  validation_key
) SELECT 
  domain,
  validation_date,
  validation_method,
  owner_verified as validation_success,
  validation_key
FROM archivetblDomains
WHERE owner_verified = TRUE AND api_enabled = TRUE;

-- update full_reindex_frequency for Full sites with new default (7 days rather than 3.5 days)

UPDATE tblDomains SET full_reindex_frequency = '7 days' WHERE full_reindex_frequency = '3.5 days';

-- Note:
-- isn't an explicit owner_verified in new schema
-- part_reindexing_frequency and part_indexing* aren't necessary at the moment as not currently used

-- 9. Copy the existing data from backuptblIndexingFilters and backuptblPermissions into the updated 
--    tblIndexingFilters and tblPermissions as per below. Note that this will this will error is there are
--    filters for domains which haven't been migrated - at the time of writing filters for domains that  
--    won't be migrated have been removed, but by the time it is run in produciton it is possible that
--    another domain might be dropped from migration e.g. due to indexing failing twice in a row.

INSERT into tblIndexingFilters (
  domain,
  action,
  type,
  value
) SELECT
  domain,
  action,
  type,
  value
FROM backuptblIndexingFilters;

INSERT into tblPermissions (
  domain,
  role
) SELECT
  domain,
  role
FROM backuptblPermissions;

-- 10. If all okay, then do the new code deployment as usual. This will start the indexing and web server.
-- 11. Delete the backup tables, but might want to keep the archivetblDomains for a while in case there are 
--     issues raised relating to the domains that weren't migrated.

DROP TABLE backuptblIndexingFilters, backuptblPermissions;

