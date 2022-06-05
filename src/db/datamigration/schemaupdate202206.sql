ALTER TABLE tblDomains 
ADD COLUMN include_in_public_search Boolean;

UPDATE tblDomains
SET include_in_public_search = TRUE
WHERE domain LIKE '%';

