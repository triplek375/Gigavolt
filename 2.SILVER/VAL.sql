# =====================================================================
# VALIDATE DATA IMPORTED IN SILVER TABLES
# =====================================================================
USE gigavolt_db;

SELECT 
    'Customers' AS data_domain, 
    (SELECT COUNT(*) FROM bronze_customers) AS bronze_count,
    (SELECT COUNT(*) FROM customers) AS silver_count,
    (SELECT COUNT(*) FROM bronze_customers) - (SELECT COUNT(*) FROM customers) AS difference
UNION ALL
SELECT 
    'Dispatches', 
    (SELECT COUNT(*) FROM bronze_dispatches),
    (SELECT COUNT(*) FROM dispatches),
    (SELECT COUNT(*) FROM bronze_dispatches) - (SELECT COUNT(*) FROM dispatches)
UNION ALL
SELECT 
    'Equipment', 
    (SELECT COUNT(*) FROM bronze_equipment),
    (SELECT COUNT(*) FROM equipment),
    (SELECT COUNT(*) FROM bronze_equipment) - (SELECT COUNT(*) FROM equipment)
UNION ALL
SELECT 
    'Parts', 
    (SELECT COUNT(*) FROM bronze_parts),
    (SELECT COUNT(*) FROM parts),
    (SELECT COUNT(*) FROM bronze_parts) - (SELECT COUNT(*) FROM parts)
UNION ALL
SELECT 
    'Warranty Claims', 
    (SELECT COUNT(*) FROM bronze_warranty_claims),
    (SELECT COUNT(*) FROM warrantyClaims),
    (SELECT COUNT(*) FROM bronze_warranty_claims) - (SELECT COUNT(*) FROM warrantyClaims);