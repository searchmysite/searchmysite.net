-- Increase number of embeddings per page, from 8 to 10 for basic listing, from 12 to 15 for free trial, and from 40 to 50 for full listing
-- To reflect changes in db/sql/init-tables.inc

UPDATE tblTiers SET default_content_chunks_limit = 10 WHERE tier = 1;
UPDATE tblTiers SET default_content_chunks_limit = 15 WHERE tier = 2;
UPDATE tblTiers SET default_content_chunks_limit = 50 WHERE tier = 3;

UPDATE tblDomains SET content_chunks_limit = 10 WHERE content_chunks_limit = 8;
UPDATE tblDomains SET content_chunks_limit = 15 WHERE content_chunks_limit = 12;
UPDATE tblDomains SET content_chunks_limit = 50 WHERE content_chunks_limit = 40;

