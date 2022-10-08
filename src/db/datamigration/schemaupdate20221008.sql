-- tblDomains: rename part_reindex_frequency to incremental_reindex_frequency
-- tblDomains: rename full_indexing_status to indexing_status
-- tblDomains: rename full_indexing_status_changed to indexing_status_changed 

ALTER TABLE tblDomains RENAME COLUMN part_reindex_frequency TO incremental_reindex_frequency;
ALTER TABLE tblDomains RENAME COLUMN full_indexing_status TO indexing_status;
ALTER TABLE tblDomains RENAME COLUMN full_indexing_status_changed TO indexing_status_changed;

-- tblDomains: rename part_indexing_status to last_index_completed
-- tblDomains: rename part_indexing_status_changed to last_full_index_completed

ALTER TABLE tblDomains RENAME COLUMN part_indexing_status TO last_index_completed;
ALTER TABLE tblDomains RENAME COLUMN part_indexing_status_changed TO last_full_index_completed;

-- change type of last_index_completed from TEXT to TIMESTAMPTZ

ALTER TABLE tblDomains ALTER COLUMN last_index_completed TYPE TIMESTAMPTZ USING last_index_completed::TIMESTAMPTZ;

-- tblTiers: rename default_part_reindex_frequency to default_incremental_reindex_frequency 

ALTER TABLE tblTiers RENAME COLUMN default_part_reindex_frequency TO default_incremental_reindex_frequency;

-- set incremental_reindex_frequency for all indexed sites (tier 1, tier 2, tier 3) and check for sites which have had indexing disabled

UPDATE tblDomains d SET full_reindex_frequency = '28 DAYS', incremental_reindex_frequency = '7 DAYS'
FROM tblListingStatus l WHERE d.domain = l.domain AND tier = 1 OR tier = 2;
UPDATE tblDomains d SET full_reindex_frequency = '7 DAYS', incremental_reindex_frequency = '1 DAY'
FROM tblListingStatus l WHERE d.domain = l.domain AND tier = 3;

-- set last_index_completed & last_full_index_completed to indexing_status_changed where indexing_status = COMPLETE

UPDATE tblDomains SET last_index_completed = indexing_status_changed, last_full_index_completed = indexing_status_changed WHERE indexing_status = 'COMPLETE';

