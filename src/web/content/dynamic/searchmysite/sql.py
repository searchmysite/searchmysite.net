# SQL for admin/add.py
# --------------------

sql_select_tiers = "SELECT tier, tier_name, default_full_reindex_frequency, default_incremental_reindex_frequency, default_indexing_page_limit, default_content_chunks_limit, default_on_demand_reindexing, default_api_enabled, cost_amount, cost_currency, listing_duration "\
    "FROM tblTiers;"

# Selects details of the highest listed tier (whether active or not)
sql_select_highest_tier = "SELECT l.status, l.tier, l.pending_state, d.moderator_approved, d.moderator_action_reason, d.indexing_enabled, d.indexing_disabled_reason, d.home_page, d.login_type, d.category FROM tblDomains d "\
    "INNER JOIN tblListingStatus l ON d.domain = l.domain "\
    "WHERE d.domain = (%s) "\
    "ORDER BY l.tier DESC LIMIT 1;"

# Selects the active tier
sql_select_active_tier = "SELECT tier FROM tblListingStatus WHERE status = 'ACTIVE' AND domain = (%s);"

sql_insert_domain = "INSERT INTO tblDomains "\
    "(domain, home_page, domain_first_submitted, category, include_in_public_search, indexing_type) "\
    "VALUES ((%s), (%s), NOW(), (%s), TRUE, 'spider/default');"

sql_insert_basic_listing = "INSERT INTO tblListingStatus (domain, tier, status, status_changed, pending_state, pending_state_changed) "\
    "VALUES ((%s), (%s), 'PENDING', NOW(), 'MODERATOR_REVIEW', NOW());"

sql_insert_freefull_listing = "INSERT INTO tblListingStatus (domain, tier, status, status_changed, pending_state, pending_state_changed) "\
    "VALUES ((%s), (%s), 'PENDING', NOW(), 'LOGIN_AND_VALIDATION_METHOD', NOW());"

sql_update_freefull_listing = "UPDATE tblListingStatus "\
    "SET status = 'PENDING', status_changed = NOW(), pending_state = 'LOGIN_AND_VALIDATION_METHOD', pending_state_changed = NOW() "\
    "WHERE domain = (%s) AND tier = (%s);"

sql_update_freefull_step1 = "UPDATE tblDomains "\
    "SET include_in_public_search = (%s), login_type = (%s) WHERE domain = (%s);"\
    "UPDATE tblListingStatus "\
    "SET pending_state = (%s), pending_state_changed = NOW() "\
    "WHERE domain = (%s) AND tier = (%s);"

sql_update_freefull_step2 = "UPDATE tblDomains "\
    "SET email = (%s), password = (%s) WHERE domain = (%s);"\
    "UPDATE tblListingStatus "\
    "SET pending_state = (%s), pending_state_changed = NOW() "\
    "WHERE domain = (%s) AND tier = (%s);"\
    "INSERT INTO tblValidations "\
    "(domain, validation_method, validation_key) "\
    "VALUES ((%s), (%s), (%s));"

sql_update_freefull_step3 = "UPDATE tblListingStatus "\
    "SET pending_state = 'PAYMENT', pending_state_changed = NOW() "\
    "WHERE domain = (%s) AND tier = (%s);"

sql_update_freefull_validated = "UPDATE tblValidations "\
    "SET validation_success = TRUE, validation_date = NOW() "\
    "WHERE domain = (%s);"

# Delete any tier 1 listings if present to avoid any potential issues later, then update the tier 2 or 3 status to 'ACTIVE'
sql_update_freefull_approved = "DELETE FROM tblListingStatus WHERE domain = (%s) AND tier = 1;"\
    "UPDATE tblListingStatus "\
    "SET status = 'ACTIVE', status_changed = NOW(), pending_state = NULL, pending_state_changed = NOW() "\
    "WHERE domain = (%s) AND tier = (%s); "\
    "UPDATE tblDomains SET "\
    "full_reindex_frequency = tblTiers.default_full_reindex_frequency, "\
    "incremental_reindex_frequency = tblTiers.default_incremental_reindex_frequency, "\
    "indexing_page_limit = tblTiers.default_indexing_page_limit, "\
    "content_chunks_limit = tblTiers.default_content_chunks_limit, "\
    "on_demand_reindexing = tblTiers.default_on_demand_reindexing, "\
    "api_enabled = tblTiers.default_api_enabled, "\
    "indexing_enabled = TRUE, "\
    "indexing_status = 'PENDING', "\
    "indexing_status_changed = NOW() "\
    "FROM tblTiers WHERE tblTiers.tier = (%s) and tblDomains.domain = (%s);"

sql_select_validation_key = "SELECT validation_key FROM tblValidations WHERE domain = (%s);"


# SQL for admin/admin.py
# ----------------------

sql_select_home_page = 'SELECT home_page FROM tblDomains WHERE domain = (%s);'

sql_select_basic_pending = "SELECT d.domain, d.home_page, d.category, d.domain_first_submitted FROM tblDomains d "\
    "INNER JOIN tblListingStatus l ON d.domain = l.domain "\
    "WHERE l.status = 'PENDING' AND l.tier = 1 AND l.pending_state = 'MODERATOR_REVIEW' "\
    "ORDER BY l.listing_end DESC, l.tier ASC;"

sql_update_basic_approved = "UPDATE tblListingStatus "\
    "SET status = 'ACTIVE', status_changed = NOW(), pending_state = NULL, pending_state_changed = NOW(), listing_start = NOW(), listing_end = NOW() + (SELECT listing_duration FROM tblTiers WHERE tier = 1) "\
    "WHERE domain = (%s) AND status = 'PENDING' AND tier = 1 AND pending_state = 'MODERATOR_REVIEW'; "\
    "UPDATE tblDomains SET "\
    "moderator_approved = TRUE, "\
    "moderator = (%s), "\
    "full_reindex_frequency = tblTiers.default_full_reindex_frequency, "\
    "incremental_reindex_frequency = tblTiers.default_incremental_reindex_frequency, "\
    "indexing_page_limit = tblTiers.default_indexing_page_limit, "\
    "content_chunks_limit = tblTiers.default_content_chunks_limit, "\
    "on_demand_reindexing = tblTiers.default_on_demand_reindexing, "\
    "api_enabled = tblTiers.default_api_enabled, "\
    "indexing_enabled = TRUE, "\
    "indexing_status = 'PENDING', "\
    "indexing_status_changed = NOW() "\
    "FROM tblTiers WHERE tblTiers.tier = 1 and tblDomains.domain = (%s);"

sql_update_basic_reject = "UPDATE tblListingStatus "\
    "SET status = 'DISABLED', status_changed = NOW(), pending_state = NULL, pending_state_changed = NOW() "\
    "WHERE domain = (%s) AND tier = 1; "\
    "UPDATE tblDomains SET "\
    "moderator_approved = FALSE, "\
    "moderator = (%s), "\
    "moderator_action_reason = (%s), "\
    "moderator_action_changed = NOW(), "\
    "indexing_enabled = FALSE, "\
    "indexing_disabled_reason = 'Moderator rejected', "\
    "indexing_disabled_changed = NOW() "\
    "WHERE domain = (%s);"


# SQL for admin/auth.py
# ---------------------

sql_select_login_details = "SELECT l.status, l.tier, d.email, d.password, d.login_type FROM tblDomains d "\
    "INNER JOIN tblListingStatus l ON d.domain = l.domain "\
    "WHERE d.domain = (%s) "\
    "ORDER BY l.tier ASC;"

sql_select_admin = "SELECT * from tblPermissions WHERE role = 'admin' AND domain = (%s);"

sql_last_login_time = "UPDATE tblDomains SET last_login = now() WHERE domain = (%s);"

sql_change_password = "UPDATE tblDomains SET password = (%s) WHERE domain = (%s);"

sql_forgotten_password = "UPDATE tblDomains SET forgotten_password_key = (%s), forgotten_password_key_expiry = now() + '30 minutes' WHERE domain = (%s);"

sql_forgotten_password_login = "SELECT * FROM tblDomains WHERE forgotten_password_key = (%s) AND forgotten_password_key_expiry < now() + '30 minutes';"


# SQL for admin/manage.py
# -----------------------

sql_select_domains = "SELECT * FROM tblDomains WHERE domain = (%s);"

sql_select_filters = "SELECT * FROM tblIndexingFilters WHERE domain = (%s);"

sql_select_subscriptions = "SELECT t.tier_name, s.subscribed, s.subscription_start, s.subscription_end, s.payment FROM tblSubscriptions s INNER JOIN tblTiers t on s.tier = t.tier WHERE DOMAIN = (%s) ORDER BY s.subscription_start ASC;"

sql_update_value = "UPDATE tblDomains SET %s = (%s) WHERE domain = (%s);"

sql_insert_filter = "INSERT INTO tblIndexingFilters VALUES ((%s), 'exclude', (%s), (%s));"

sql_delete_filter = "DELETE FROM tblIndexingFilters WHERE domain = (%s) AND action = 'exclude' AND type = (%s) AND VALUE = (%s);"

sql_update_indexing_status = "UPDATE tblDomains SET indexing_status = 'PENDING', indexing_status_changed = now() WHERE domain = (%s); "\
    "INSERT INTO tblIndexingLog VALUES ((%s), 'PENDING', now());"

sql_select_tier = "SELECT l.status, l.tier, t.tier_name, l.listing_end FROM tblListingStatus l INNER JOIN tblTiers t ON t.tier = l.tier WHERE l.domain = (%s) AND l.status = 'ACTIVE' ORDER BY tier DESC LIMIT 1;"

sql_upgrade_tier2_to_tier3 = "UPDATE tblListingStatus SET status = 'EXPIRED', status_changed = NOW() WHERE domain = (%s) AND tier = 2; "\
    "INSERT INTO tblListingStatus (domain, tier, status, status_changed, listing_start, listing_end) "\
    "VALUES ((%s), 3, 'ACTIVE', NOW(), NOW(), NOW() + (SELECT listing_duration FROM tblTiers WHERE tier = 3)) "\
    "  ON CONFLICT (domain, tier) "\
    "  DO UPDATE SET "\
    "    status = EXCLUDED.status, "\
    "    status_changed = EXCLUDED.status_changed, "\
    "    listing_start = EXCLUDED.listing_start, "\
    "    listing_end = EXCLUDED.listing_end; "\
    "UPDATE tblDomains SET "\
    "full_reindex_frequency = tblTiers.default_full_reindex_frequency, "\
    "incremental_reindex_frequency = tblTiers.default_incremental_reindex_frequency, "\
    "indexing_page_limit = tblTiers.default_indexing_page_limit, "\
    "content_chunks_limit = tblTiers.default_content_chunks_limit, "\
    "on_demand_reindexing = tblTiers.default_on_demand_reindexing, "\
    "indexing_status = 'PENDING', "\
    "indexing_status_changed = NOW() "\
    "FROM tblTiers WHERE tblTiers.tier = 3 and tblDomains.domain = (%s);"


# SQL for adminutils.py
# ---------------------

sql_select_domains_allowing_subdomains = "SELECT setting_value FROM tblSettings WHERE setting_name = 'domain_allowing_subdomains';"

# Delete tables with foreign keys before finally deleting from tblDomains
# Note there may still be references to the domain in tblSubscriptions and tblIndexingLog, but we want to keep those and they don't have a foreign key
sql_delete_domain = "DELETE FROM tblValidations WHERE domain = (%s); DELETE FROM tblPermissions WHERE domain = (%s); DELETE FROM tblListingStatus WHERE domain = (%s); DELETE FROM tblIndexingFilters WHERE domain = (%s); DELETE FROM tblDomains WHERE domain = (%s);"

# The SELECT coalesce(MAX(subscription_end),NOW()) AS subscription_end FROM tblSubscriptions WHERE domain = (%s) AND subscription_end > NOW()
# returns the latest subscription end date, if the subscription end date is in the future, or NOW() if none is set, so that subscriptions can be "stacked"
sql_insert_full_subscription = "INSERT INTO tblSubscriptions (domain, tier, subscribed, subscription_start, subscription_end, payment, payment_id) "\
    "VALUES ((%s), (%s), NOW(), "\
        "(SELECT coalesce(MAX(subscription_end),NOW()) AS subscription_end FROM tblSubscriptions WHERE domain = (%s) AND subscription_end > NOW()), "\
        "(SELECT coalesce(MAX(subscription_end),NOW()) AS subscription_end FROM tblSubscriptions WHERE domain = (%s) AND subscription_end > NOW()) + (SELECT listing_duration FROM tblTiers WHERE tier = (%s)), "\
        "(SELECT cost_amount FROM tblTiers WHERE tier = (%s)), (%s));"

sql_update_full_listing_startandend = "UPDATE tblListingStatus "\
    "SET listing_start = NOW(), "\
        "listing_end = (SELECT MAX(subscription_end) FROM tblSubscriptions WHERE domain = (%s)) "\
    "WHERE domain = (%s) AND tier = (%s);"

sql_update_free_listing_startandend = "UPDATE tblListingStatus "\
    "SET listing_start = NOW(), "\
        "listing_end = NOW() + (SELECT listing_duration FROM tblTiers WHERE tier = (%s)) "\
    "WHERE domain = (%s) AND tier = (%s);"


# SQL for searchutils.py
# ----------------------

sql_check_api_enabled = "SELECT api_enabled FROM tblDomains WHERE domain = (%s);"
