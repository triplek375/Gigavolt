# =====================================================================
# CLEAN AND TRANSFER DATA TO SILVER TABLES
# =====================================================================
USE gigavolt_db;


# =====================================================================
# Customer and its Lookup Tables
# =====================================================================

INSERT INTO companies (company_name)
SELECT DISTINCT 
    TRIM(REGEXP_REPLACE(company_name, '<[^>]+>', '')) AS company_name
FROM bronze_customers
ON DUPLICATE KEY UPDATE company_name = VALUES(company_name);

INSERT INTO countries (country_name)
SELECT DISTINCT 
    CASE 
        WHEN country IS NULL OR TRIM(country) = '' OR country IN ('US', 'USA') THEN 'United States'
        ELSE TRIM(country)
    END AS country_name
FROM bronze_customers
ON DUPLICATE KEY UPDATE country_name = VALUES(country_name);

INSERT INTO states (state_name, country_id)
SELECT DISTINCT 
    UPPER(TRIM(b.state)) AS state_name,
    c.country_id
FROM bronze_customers b
JOIN countries c ON c.country_name = 
    CASE 
        WHEN b.country IS NULL OR TRIM(b.country) = '' OR b.country IN ('US', 'USA') THEN 'United States'
        ELSE TRIM(b.country)
    END
ON DUPLICATE KEY UPDATE state_name = VALUES(state_name);

INSERT INTO cities (city_name, state_id)
SELECT DISTINCT 
    TRIM(b.city) AS city_name,
    s.state_id
FROM bronze_customers b
JOIN states s ON s.state_name = UPPER(TRIM(b.state))
ON DUPLICATE KEY UPDATE city_name = VALUES(city_name);

INSERT INTO locations (zip, city_id)
SELECT DISTINCT 
    LPAD(CAST(b.zip AS CHAR), 5, '0') AS zip,
    ci.city_id
FROM bronze_customers b
JOIN states s ON s.state_name = UPPER(TRIM(b.state))
JOIN cities ci ON ci.city_name = TRIM(b.city) AND ci.state_id = s.state_id
ON DUPLICATE KEY UPDATE zip = VALUES(zip);

INSERT INTO customerStatus (status_name)
SELECT DISTINCT 
    TRIM(status) AS status_name
FROM bronze_customers
ON DUPLICATE KEY UPDATE status_name = VALUES(status_name);

INSERT INTO customers (
    customer_id,
    first_name,
    last_name,
    company_id,
    phone,
    email,
    address,
    location_id,
    created_date,
    status_id
)
SELECT 
    b.customer_id,
    -- Extract first word from contact_name as first_name
    SUBSTRING_INDEX(TRIM(REGEXP_REPLACE(b.contact_name, '\\s+', ' ')), ' ', 1) AS first_name,
    -- Extract remaining words as last_name
    SUBSTRING(TRIM(REGEXP_REPLACE(b.contact_name, '\\s+', ' ')) FROM LOCATE(' ', TRIM(REGEXP_REPLACE(b.contact_name, '\\s+', ' '))) + 1) AS last_name,
    comp.company_id,
    REGEXP_REPLACE(b.phone, '[^0-9+]', '') AS phone,
    LOWER(TRIM(b.email)) AS email,
    -- Strip HTML tags from address
    TRIM(REGEXP_REPLACE(b.address, '<[^>]+>', '')) AS address,
    l.location_id,
    -- Standardize mixed date formats into DATE type
    CAST(
        CASE 
            WHEN b.created_date LIKE '____/%/%' THEN STR_TO_DATE(b.created_date, '%Y/%m/%d')
            WHEN b.created_date LIKE '%/%/%' THEN STR_TO_DATE(b.created_date, '%m/%d/%Y')
            WHEN b.created_date LIKE '%-%-%' AND LENGTH(b.created_date) = 10 AND b.created_date LIKE '____-%-%' THEN STR_TO_DATE(b.created_date, '%Y-%m-%d')
            WHEN b.created_date LIKE '%-%-%' AND LENGTH(b.created_date) = 10 THEN STR_TO_DATE(b.created_date, '%m-%d-%Y')
            WHEN b.created_date LIKE '%T%' THEN STR_TO_DATE(SUBSTRING_INDEX(b.created_date, 'T', 1), '%Y-%m-%d')
            ELSE STR_TO_DATE(b.created_date, '%Y/%m/%d')
        END AS DATE
    ) AS created_date,
    cs.status_id
FROM bronze_customers b
JOIN companies comp ON comp.company_name = TRIM(REGEXP_REPLACE(b.company_name, '<[^>]+>', ''))
JOIN customerStatus cs ON cs.status_name = TRIM(b.status)
JOIN states s ON s.state_name = UPPER(TRIM(b.state))
JOIN cities ci ON ci.city_name = TRIM(b.city) AND ci.state_id = s.state_id
JOIN locations l ON l.zip = LPAD(CAST(b.zip AS CHAR), 5, '0') AND l.city_id = ci.city_id
ON DUPLICATE KEY UPDATE 
    first_name = VALUES(first_name),
    last_name = VALUES(last_name),
    company_id = VALUES(company_id),
    phone = VALUES(phone),
    email = VALUES(email),
    address = VALUES(address),
    location_id = VALUES(location_id),
    created_date = VALUES(created_date),
    status_id = VALUES(status_id);

# =====================================================================
# Equipment and its Lookup Tables
# =====================================================================

INSERT INTO equipmentModels (model_name, capacity_kw, voltage)
SELECT DISTINCT 
    NULLIF(TRIM(model), '') AS model_name,
    CAST(capacity_kw AS DECIMAL(10,2)) AS capacity_kw,
    CAST(REPLACE(voltage, 'V', '') AS DECIMAL(10,2)) AS voltage
FROM bronze_equipment;

INSERT INTO equipmentStatus (status_name)
SELECT DISTINCT 
    CASE 
        WHEN LOWER(status) LIKE '%service%' THEN 'In Service'
        WHEN LOWER(status) LIKE '%decommissioned%' THEN 'Decommissioned'
        ELSE CONCAT(UPPER(SUBSTRING(status, 1, 1)), LOWER(SUBSTRING(status, 2)))
    END AS status_name
FROM bronze_equipment;

INSERT INTO equipment (
    equipment_id,
    customer_id,
    model_id,
    serial_number,
    install_date,
    warranty_expiration,
    status_id,
    location_notes
)
SELECT DISTINCT
    CAST(b.equipment_id AS CHAR) AS equipment_id,
    b.customer_id,
    m.model_id,
    COALESCE(NULLIF(TRIM(b.serial_number), ''), 'UNKNOWN') AS serial_number,
    CAST(
        CASE 
            WHEN b.install_date LIKE '____/%/%' THEN STR_TO_DATE(b.install_date, '%Y/%m/%d')
            WHEN b.install_date LIKE '%/%/%' THEN STR_TO_DATE(b.install_date, '%m/%d/%Y')
            WHEN b.install_date LIKE '%-%-%' AND LENGTH(b.install_date) >= 10 AND b.install_date LIKE '____-%-%' THEN STR_TO_DATE(SUBSTRING(b.install_date, 1, 10), '%Y-%m-%d')
            WHEN b.install_date LIKE '%-%-%' AND LENGTH(b.install_date) >= 10 THEN STR_TO_DATE(SUBSTRING(b.install_date, 1, 10), '%m-%d-%Y')
            WHEN b.install_date LIKE '%T%' THEN STR_TO_DATE(SUBSTRING_INDEX(b.install_date, 'T', 1), '%Y-%m-%d')
            ELSE STR_TO_DATE(SUBSTRING(b.install_date, 1, 10), '%Y/%m/%d')
        END AS DATE
    ) AS install_date,
    CAST(
        CASE 
            WHEN b.warranty_expiration LIKE '____/%/%' THEN STR_TO_DATE(b.warranty_expiration, '%Y/%m/%d')
            WHEN b.warranty_expiration LIKE '%/%/%' THEN STR_TO_DATE(b.warranty_expiration, '%m/%d/%Y')
            WHEN b.warranty_expiration LIKE '%-%-%' AND LENGTH(b.warranty_expiration) >= 10 AND b.warranty_expiration LIKE '____-%-%' THEN STR_TO_DATE(SUBSTRING(b.warranty_expiration, 1, 10), '%Y-%m-%d')
            WHEN b.warranty_expiration LIKE '%-%-%' AND LENGTH(b.warranty_expiration) >= 10 THEN STR_TO_DATE(SUBSTRING(b.warranty_expiration, 1, 10), '%m-%d-%Y')
            WHEN b.warranty_expiration LIKE '%T%' THEN STR_TO_DATE(SUBSTRING_INDEX(b.warranty_expiration, 'T', 1), '%Y-%m-%d')
            ELSE STR_TO_DATE(SUBSTRING(b.warranty_expiration, 1, 10), '%Y/%m/%d')
        END AS DATE
    ) AS warranty_expiration,
    s.status_id,
    NULLIF(TRIM(MIN(b.location_notes)), '') AS location_notes
FROM bronze_equipment b
JOIN equipmentModels m 
    ON CAST(b.capacity_kw AS DECIMAL(10,2)) = m.capacity_kw 
   AND CAST(REPLACE(b.voltage, 'V', '') AS DECIMAL(10,2)) = m.voltage
JOIN equipmentStatus s 
    ON s.status_name = CASE 
        WHEN LOWER(b.status) LIKE '%service%' THEN 'In Service'
        WHEN LOWER(b.status) LIKE '%decommissioned%' THEN 'Decommissioned'
        ELSE CONCAT(UPPER(SUBSTRING(b.status, 1, 1)), LOWER(SUBSTRING(b.status, 2)))
    END
GROUP BY TRIM(b.equipment_id), s.status_id, m.model_id
ON DUPLICATE KEY UPDATE 
    customer_id = VALUES(customer_id),
    model_id = VALUES(model_id),
    serial_number = VALUES(serial_number),
    install_date = VALUES(install_date),
    warranty_expiration = VALUES(warranty_expiration),
    location_notes = VALUES(location_notes);

# =====================================================================
# Dispatches and its Lookup Tables
# =====================================================================

INSERT INTO technicians (first_name, last_name)
SELECT DISTINCT 
    COALESCE(
        SUBSTRING_INDEX(TRIM(REGEXP_REPLACE(technician, '\\s+', ' ')), ' ', 1), 
        'Unknown'
    ) AS first_name,
    COALESCE(
        SUBSTRING_INDEX(TRIM(REGEXP_REPLACE(technician, '\\s+', ' ')), ' ', -1), 
        'Unknown'
    ) AS last_name
FROM bronze_dispatches
WHERE technician IS NOT NULL AND TRIM(technician) != ''
UNION
SELECT 'Unknown', 'Unknown'
FROM (SELECT 1) t
WHERE NOT EXISTS (SELECT 1 FROM technicians WHERE first_name = 'Unknown' AND last_name = 'Unknown');

INSERT INTO serviceTypes (service_type_name)
SELECT DISTINCT TRIM(service_type)
FROM bronze_dispatches
WHERE service_type IS NOT NULL AND TRIM(service_type) != '';

INSERT INTO dispatchStatus (status_name)
SELECT DISTINCT 
    CASE 
        WHEN LOWER(TRIM(status)) = 'completed' THEN 'Completed'
        WHEN LOWER(TRIM(status)) = 'pending' THEN 'Pending'
        WHEN LOWER(TRIM(status)) = 'cancelled' THEN 'Cancelled'
        WHEN LOWER(TRIM(status)) = 'in progress' THEN 'In Progress'
        ELSE CONCAT(UPPER(LEFT(TRIM(status), 1)), LOWER(SUBSTRING(TRIM(status), 2)))
    END
FROM bronze_dispatches
WHERE status IS NOT NULL AND TRIM(status) != '';

INSERT INTO dispatches (
    dispatch_id, 
    equipment_id, 
    dispatch_date, 
    technician_id, 
    service_type_id, 
    hours_spent, 
    labor_cost, 
    resolution_summary, 
    status_id
)
<#if false>...</#if>SELECT 
    b.dispatch_id,
    b.equipment_id,
    -- Handle multiple date formats safely
    CASE 
        WHEN b.dispatch_date LIKE '%/%/%' THEN STR_TO_DATE(b.dispatch_date, '%m/%d/%Y')
        WHEN b.dispatch_date LIKE '%-%-%' AND LENGTH(b.dispatch_date) >= 10 THEN STR_TO_DATE(LEFT(b.dispatch_date, 10), '%Y-%m-%d')
        ELSE STR_TO_DATE(LEFT(b.dispatch_date, 10), '%m-%d-%Y')
    END AS dispatch_date,
    COALESCE(t.technician_id, (SELECT technician_id FROM technicians WHERE first_name = 'Unknown' LIMIT 1)) AS technician_id,
    s.service_type_id,
    CAST(b.hours_spent AS DECIMAL(10,2)) AS hours_spent,
    -- Strip currency symbols and cast to decimal
    CAST(REPLACE(b.labor_cost, '$', '') AS DECIMAL(10,2)) AS labor_cost,
    b.resolution_summary,
    st.status_id
FROM bronze_dispatches b
LEFT JOIN technicians t 
    ON TRIM(REGEXP_REPLACE(b.technician, '\\s+', ' ')) = CONCAT(t.first_name, ' ', t.last_name)
JOIN serviceTypes s 
    ON TRIM(b.service_type) = s.service_type_name
JOIN dispatchStatus st 
    ON CASE 
        WHEN LOWER(TRIM(b.status)) = 'completed' THEN 'Completed'
        WHEN LOWER(TRIM(b.status)) = 'pending' THEN 'Pending'
        WHEN LOWER(TRIM(b.status)) = 'cancelled' THEN 'Cancelled'
        WHEN LOWER(TRIM(b.status)) = 'in progress' THEN 'In Progress'
        ELSE CONCAT(UPPER(LEFT(TRIM(b.status), 1)), LOWER(SUBSTRING(TRIM(b.status), 2)))
    END = st.status_name;

# =====================================================================
# Parts and its Lookup Tables
# =====================================================================

INSERT INTO partCategories (category_name)
SELECT DISTINCT TRIM(category)
FROM bronze_parts_table
WHERE category IS NOT NULL AND TRIM(category) != ''
ON DUPLICATE KEY UPDATE category_name = VALUES(category_name);

INSERT INTO manufacturers (manufacturer_name)
SELECT DISTINCT TRIM(manufacturer)
FROM bronze_parts_table
WHERE manufacturer IS NOT NULL AND TRIM(manufacturer) != ''
ON DUPLICATE KEY UPDATE manufacturer_name = VALUES(manufacturer_name);

INSERT INTO suppliers (supplier_name)
SELECT DISTINCT TRIM(supplier)
FROM bronze_parts_table
WHERE supplier IS NOT NULL AND TRIM(supplier) != ''
ON DUPLICATE KEY UPDATE supplier_name = VALUES(supplier_name);

INSERT INTO parts (
    part_id,
    part_name,
    category_id,
    manufacturer_id,
    supplier_id,
    unit_cost,
    unit_price,
    stock_quantity,
    reorder_level
)
SELECT 
    TRIM(b.part_id),
    TRIM(b.part_name),
    c.category_id,
    m.manufacturer_id,
    s.supplier_id,
    CAST(b.unit_cost AS DECIMAL(10,2)),
    CAST(b.unit_price AS DECIMAL(10,2)),
    CAST(b.stock_quantity AS SIGNED),
    CAST(b.reorder_level AS SIGNED)
FROM bronze_parts_table b
JOIN partCategories c ON TRIM(b.category) = c.category_name
JOIN manufacturers m ON TRIM(b.manufacturer) = m.manufacturer_name
JOIN suppliers s ON TRIM(b.supplier) = s.supplier_name
ON DUPLICATE KEY UPDATE
    part_name = VALUES(part_name),
    category_id = VALUES(category_id),
    manufacturer_id = VALUES(manufacturer_id),
    supplier_id = VALUES(supplier_id),
    unit_cost = VALUES(unit_cost),
    unit_price = VALUES(unit_price),
    stock_quantity = VALUES(stock_quantity),
    reorder_level = VALUES(reorder_level);

# =====================================================================
# Warranty Claims and its Lookup Tables
# =====================================================================

INSERT INTO claimStatus (status_name)
SELECT DISTINCT 
    CASE 
        WHEN UPPER(TRIM(status)) = 'APPROVED' THEN 'Approved'
        WHEN UPPER(TRIM(status)) = 'PENDING' THEN 'Pending'
        WHEN UPPER(TRIM(status)) = 'REJECTED' THEN 'Rejected'
        WHEN UPPER(TRIM(status)) = 'UNDER REVIEW' THEN 'Under Review'
        ELSE CONCAT(UPPER(LEFT(TRIM(status), 1)), LOWER(SUBSTRING(TRIM(status), 2)))
    END AS normalized_status
FROM bronze_warranty_claims
WHERE status IS NOT NULL AND TRIM(status) != ''
ON DUPLICATE KEY UPDATE status_name = status_name;

INSERT INTO warrantyClaims (
    claim_id,
    equipment_id,
    dispatch_id,
    part_id,
    claim_date,
    claim_amount,
    approved_amount,
    status_id,
    denial_reason,
    claim_notes
)
SELECT 
    TRIM(b.claim_id),
    TRIM(b.equipment_id),
    NULLIF(TRIM(b.dispatch_id), ''),
    NULLIF(TRIM(b.part_id), ''),
    -- Robust multi-format date parser for bronze text fields
    COALESCE(
        STR_TO_DATE(SUBSTRING(b.claim_date, 1, 10), '%Y-%m-%d'),
        STR_TO_DATE(SUBSTRING(b.claim_date, 1, 10), '%Y/%m/%d'),
        STR_TO_DATE(SUBSTRING(b.claim_date, 1, 10), '%m/%d/%Y'),
        STR_TO_DATE(SUBSTRING(b.claim_date, 1, 10), '%d-%m-%Y')
    ) AS claim_date,
    CAST(b.claim_amount AS DECIMAL(10,2)),
    CASE 
        WHEN TRIM(b.approved_amount) = '' OR b.approved_amount IS NULL THEN NULL 
        ELSE CAST(b.approved_amount AS DECIMAL(10,2))
    END AS approved_amount,
    cs.status_id,
    NULLIF(TRIM(b.denial_reason), ''),
    TRIM(b.claim_notes)
FROM bronze_warranty_claims b
JOIN claimStatus cs ON cs.status_name = 
    CASE 
        WHEN UPPER(TRIM(b.status)) = 'APPROVED' THEN 'Approved'
        WHEN UPPER(TRIM(b.status)) = 'PENDING' THEN 'Pending'
        WHEN UPPER(TRIM(b.status)) = 'REJECTED' THEN 'Rejected'
        WHEN UPPER(TRIM(b.status)) = 'UNDER REVIEW' THEN 'Under Review'
        ELSE CONCAT(UPPER(LEFT(TRIM(b.status), 1)), LOWER(SUBSTRING(TRIM(b.status), 2)))
    END;