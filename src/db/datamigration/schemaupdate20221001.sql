ALTER TABLE tblDomains 
DROP COLUMN IF EXISTS rss_feed,
DROP COLUMN IF EXISTS sitemap;

ALTER TABLE tblDomains 
ADD COLUMN web_feed_auto_discovered TEXT,
ADD COLUMN web_feed_user_entered TEXT,
ADD COLUMN sitemap_auto_discovered TEXT,
ADD COLUMN sitemap_user_entered TEXT;

