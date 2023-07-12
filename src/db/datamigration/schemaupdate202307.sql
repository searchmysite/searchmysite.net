ALTER TABLE tblDomains 
ADD COLUMN content_chunks_limit SMALLINT;

UPDATE tblDomains SET content_chunks_limit =  8 WHERE indexing_page_limit =  50;
UPDATE tblDomains SET content_chunks_limit = 12 WHERE indexing_page_limit = 100;
UPDATE tblDomains SET content_chunks_limit = 40 WHERE indexing_page_limit = 500;

ALTER TABLE tblTiers
ADD COLUMN default_content_chunks_limit SMALLINT;

UPDATE tblTiers SET default_content_chunks_limit =  8 WHERE tier = 1;
UPDATE tblTiers SET default_content_chunks_limit = 12 WHERE tier = 2;
UPDATE tblTiers SET default_content_chunks_limit = 40 WHERE tier = 3;

