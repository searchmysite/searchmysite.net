-- tblDomains contains the fields which will only have one value per domain, and persist even if paid listings expire.
-- Fields relating to the listing status, which may have different values per tier for a domain, e.g. a domain could be ACTIVE on tier 1 but PENDING on tier 3, are in tblListingStatus
-- Fields which may have multiple values per domain, e.g. subscription start and end date if there are multiple subscriptions, are in tblSubscriptions
-- The fields which were in tblDomains but have since been moved to other tables are:
-- expire_date, listing_end in tblListingStatus
-- owner_verified, validation_key, validation_method & validation_date - tblValidations
-- indexing_enabled, indexing_disabled_date and indexing_disabled_reason - tblListingStatus
CREATE TABLE tblDomains (
  domain TEXT PRIMARY KEY,
  home_page TEXT,
  category TEXT,
  domain_first_submitted TIMESTAMPTZ, -- first submitted is a fixed time, and slightly different from first indexed
  login_type TEXT, -- INDIEAUTH or PASSWORD
  email TEXT,
  include_in_public_search BOOLEAN,
  password TEXT, -- only where login_type = PASSWORD
  web_feed_auto_discovered TEXT,
  web_feed_user_entered TEXT,
  sitemap_auto_discovered TEXT,
  sitemap_user_entered TEXT,
  moderator_approved BOOLEAN, -- NULL when listing created, TRUE or FALSE when Basic tier reviewed (typically remaining NULL for Free and Full tier)
  moderator_action_reason TEXT, -- only set when moderator_approved = FALSE
  moderator_action_changed TIMESTAMPTZ, 
  moderator TEXT, -- domain of moderator
  full_reindex_frequency INTERVAL,
  incremental_reindex_frequency INTERVAL,
  indexing_page_limit SMALLINT,
  content_chunks_limit SMALLINT,
  on_demand_reindexing BOOLEAN,
  api_enabled BOOLEAN,
  indexing_enabled BOOLEAN,
  indexing_disabled_reason TEXT, -- only set when indexing_enabled = FALSE
  indexing_disabled_changed TIMESTAMPTZ,
  indexing_type TEXT, -- Just 'spider/default' now, but there was a 'bulkimport/wikipedia'
  indexing_status TEXT, -- 'PENDING', 'RUNNING', 'COMPLETE'
  indexing_status_changed TIMESTAMPTZ,
  last_index_completed TIMESTAMPTZ,
  last_full_index_completed TIMESTAMPTZ,
  last_login TIMESTAMPTZ,
  forgotten_password_key TEXT,
  forgotten_password_key_expiry TIMESTAMPTZ
);

CREATE TABLE tblTiers (
  tier SMALLINT PRIMARY KEY,
  tier_name TEXT,
  default_full_reindex_frequency INTERVAL,
  default_incremental_reindex_frequency INTERVAL,
  default_indexing_page_limit SMALLINT,
  default_content_chunks_limit SMALLINT,
  default_on_demand_reindexing BOOLEAN,
  default_api_enabled BOOLEAN,
  cost_amount DECIMAL(5,2),
  cost_currency TEXT,
  listing_duration INTERVAL
);

CREATE TABLE tblListingStatus (
  domain TEXT NOT NULL,
  tier SMALLINT NOT NULL,
  status TEXT, -- PENDING, ACTIVE, DISABLED, EXPIRED
  status_changed TIMESTAMPTZ,
  pending_state TEXT, -- MODERATOR_REVIEW, LOGIN_AND_VALIDATION_METHOD, EMAIL, EMAIL_AND_PASSWORD, INDIEAUTH_LOGIN, VALIDATION_CHECK, PAYMENT, (NULL if not PENDING)
  pending_state_changed TIMESTAMPTZ,
  listing_start TIMESTAMPTZ, -- set when ACTIVE
  listing_end TIMESTAMPTZ, -- set when ACTIVE
  PRIMARY KEY (domain, tier),
  CONSTRAINT listings_domain_fk FOREIGN KEY (domain)
    REFERENCES tblDomains (domain) MATCH SIMPLE
    ON UPDATE NO ACTION ON DELETE NO ACTION,
  CONSTRAINT listings_tier_fk FOREIGN KEY (tier)
    REFERENCES tblTiers (tier) MATCH SIMPLE
    ON UPDATE NO ACTION ON DELETE NO ACTION
);
-- Note 1: The primary key on both domain and tier means a domain should only have one status per tier 
-- Note 2: On expiry, the tier will have status EXPIRED, and the tier below will become ACTIVE
-- Note 3: If a user has purchased one subscription the listing_end = listing_start + listing_duration, but if they have purchased additional subscriptions the listing_end will reflect the last subscription end

CREATE TABLE tblSubscriptions (
  subscription_id INT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  domain TEXT NOT NULL,
  tier SMALLINT NOT NULL,
  subscribed TIMESTAMPTZ,
  subscription_start TIMESTAMPTZ,
  subscription_end TIMESTAMPTZ,
  payment DECIMAL(5,2),
  payment_id TEXT,
  CONSTRAINT subscriptions_tier_fk FOREIGN KEY (tier)
    REFERENCES tblTiers (tier) MATCH SIMPLE
    ON UPDATE NO ACTION ON DELETE NO ACTION
);

CREATE TABLE tblValidations (
  domain TEXT NOT NULL,
  validation_date TIMESTAMPTZ,
  validation_method TEXT, -- INDIEAUTH or DCV
  validation_success BOOLEAN,
  validation_key TEXT, -- only for DCV
  CONSTRAINT validations_domain_fk FOREIGN KEY (domain)
    REFERENCES tblDomains (domain) MATCH SIMPLE
    ON UPDATE NO ACTION ON DELETE NO ACTION
);

CREATE TABLE tblIndexingFilters (
  domain TEXT NOT NULL,
  action VARCHAR(8),
  type VARCHAR(8),
  value TEXT,
  CONSTRAINT filters_domain_fk FOREIGN KEY (domain)
    REFERENCES tblDomains (domain) MATCH SIMPLE
    ON UPDATE NO ACTION ON DELETE NO ACTION
);

CREATE TABLE tblIndexingLog (
  domain TEXT NOT NULL,
  status TEXT,
  timestamp TIMESTAMPTZ,
  message TEXT
);

CREATE TABLE tblPermissions (
  domain TEXT NOT NULL,
  role TEXT,
  CONSTRAINT permissions_domain_fk FOREIGN KEY (domain)
    REFERENCES tblDomains (domain) MATCH SIMPLE
    ON UPDATE NO ACTION ON DELETE NO ACTION
);

CREATE TABLE tblSettings (
  setting_name TEXT NOT NULL,
  setting_value TEXT NOT NULL
);

INSERT INTO tblTiers 
(tier, tier_name, default_full_reindex_frequency, default_incremental_reindex_frequency, default_indexing_page_limit, default_content_chunks_limit, default_on_demand_reindexing, default_api_enabled, cost_amount, cost_currency, listing_duration) 
VALUES 
(1, 'Basic',      '28 days',  '14 days',  50,  8, FALSE, FALSE,  0.00, '£', '1 year'),
(2, 'Free Trial', '28 days',  '14 days', 100, 12, FALSE, TRUE,   0.00, '£', '1 month'),
(3, 'Full',        '7 days', '3.5 days', 500, 40, TRUE,  TRUE,  12.00, '£', '1 year');

INSERT INTO tblSettings 
(setting_name, setting_value) 
VALUES 
('domain_allowing_subdomains', 'github.io'),
('domain_allowing_subdomains', 'gitlab.io'),
('domain_allowing_subdomains', 'netlify.app'),
('domain_allowing_subdomains', 'codeberg.page'),
('domain_allowing_subdomains', 'flounder.online'),
('domain_allowing_subdomains', 'neocities.org'),
('domain_allowing_subdomains', 'writeas.com'),
('domain_allowing_subdomains', 'now.sh'),
('domain_allowing_subdomains', 'tumblr.com'),
('domain_allowing_subdomains', 'tripod.com'),
('domain_allowing_subdomains', 'bitbucket.io'),
('domain_allowing_subdomains', 'eu.org'),
('domain_allowing_subdomains', 'mataroa.blog'),
('domain_allowing_subdomains', 'substack.com'),
('domain_allowing_subdomains', 'ghost.io'),
('domain_allowing_subdomains', 'blogspot.com'),
('domain_allowing_subdomains', 'bearblog.dev')

