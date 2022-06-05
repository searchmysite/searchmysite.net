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
  moderator_approved Boolean,
  moderator_action_date TIMESTAMPTZ,
  moderator_action_reason TEXT,
  moderator_action_user TEXT,
  indexing_enabled Boolean,
  indexing_disabled_date TIMESTAMPTZ,
  indexing_disabled_reason TEXT,
  indexing_type TEXT,
  indexing_frequency INTERVAL,
  indexing_page_limit SMALLINT,
  indexing_current_status TEXT,
  indexing_status_last_updated TIMESTAMPTZ,
  include_in_public_search Boolean,
  password TEXT,
  last_login TIMESTAMPTZ,
  forgotten_password_key TEXT,
  forgotten_password_key_expiry TIMESTAMPTZ
);

CREATE TABLE tblIndexingFilters (
  domain TEXT NOT NULL,
  action VARCHAR(8),
  type VARCHAR(8),
  value TEXT,
  CONSTRAINT domain_fkey FOREIGN KEY (domain)
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
  CONSTRAINT domain_fkey FOREIGN KEY (domain)
    REFERENCES tblDomains (domain) MATCH SIMPLE
    ON UPDATE NO ACTION ON DELETE NO ACTION
);

CREATE TABLE tblSettings (
  setting_name TEXT NOT NULL,
  setting_value TEXT NOT NULL
);

