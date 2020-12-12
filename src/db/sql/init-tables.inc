CREATE TABLE tblIndexedDomains (
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
  indexing_frequency INTERVAL,
  indexing_page_limit SMALLINT,
  indexing_current_status TEXT,
  indexing_status_last_updated TIMESTAMPTZ,
  password TEXT,
  last_login TIMESTAMPTZ,
  forgotten_password_key TEXT,
  forgotten_password_key_expiry TIMESTAMPTZ
);

CREATE TABLE tblPendingDomains (
  domain TEXT PRIMARY KEY,
  home_page TEXT NOT NULL,
  contact_email TEXT,
  site_category TEXT,
  date_domain_added TIMESTAMPTZ,
  owner_submitted Boolean,
  owner_verified Boolean,
  submission_method TEXT,
  validation_key TEXT,
  password TEXT
);

CREATE TABLE tblExcludeDomains (
  domain TEXT PRIMARY KEY,
  home_page TEXT NOT NULL,
  reason TEXT,
  exclusion_date TIMESTAMPTZ
);

CREATE TABLE tblIndexingFilters (
  domain TEXT NOT NULL,
  action VARCHAR(8),
  type VARCHAR(8),
  value TEXT,
  CONSTRAINT domain_fkey FOREIGN KEY (domain)
    REFERENCES tblIndexedDomains (domain) MATCH SIMPLE
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
    REFERENCES tblIndexedDomains (domain) MATCH SIMPLE
    ON UPDATE NO ACTION ON DELETE NO ACTION
);

CREATE TABLE tblSettings (
  setting_name TEXT NOT NULL,
  setting_value TEXT NOT NULL
);

