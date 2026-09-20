-- =====================================================================
-- VALIDATING VIEWS FOR TECHNICIAN
-- =====================================================================
USE gigavolt_db;

-- If logged in as 'tech_user', this will SUCCEED:
SELECT * FROM gigavolt_db.vw_customers_operational LIMIT 3 \G ;

-- If logged in as 'tech_user', this will FAIL with an access denied error:
SELECT * FROM gigavolt_db.customers LIMIT 3 \G;