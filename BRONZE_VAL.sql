# =====================================================================
# VALIDATE DATA IMPORTED IN BRONZE TABLES
# =====================================================================
USE gigavolt_db;

SELECT 'bronze_customers' AS table_name, COUNT(*) AS row_count FROM bronze_customers
UNION ALL
SELECT 'bronze_dispatches', COUNT(*) FROM bronze_dispatches
UNION ALL
SELECT 'bronze_equipment', COUNT(*) FROM bronze_equipment
UNION ALL
SELECT 'bronze_parts', COUNT(*) FROM bronze_parts
UNION ALL
SELECT 'bronze_warranty_claims', COUNT(*) FROM bronze_warranty_claims;