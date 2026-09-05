# =====================================================================
# DEFINE DATABASE
# =====================================================================
DROP DATABASE IF EXISTS gigavolt_db;
CREATE DATABASE gigavolt_db;
USE gigavolt_db;

# =====================================================================
# DEFINE BRONZE TABLES
# =====================================================================
DROP TABLE IF EXISTS bronze_customers;
CREATE TABLE bronze_customers (
    customer_id TEXT,
    company_name TEXT,
    contact_name TEXT,
    phone TEXT,
    email TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    zip TEXT,
    country TEXT,
    created_date TEXT,
    status TEXT
);

DROP TABLE IF EXISTS bronze_dispatches;
CREATE TABLE bronze_dispatches (
    dispatch_id TEXT,
    equipment_id TEXT,
    customer_id TEXT,
    dispatch_date TEXT,
    technician TEXT,
    service_type TEXT,
    hours_spent TEXT,
    labor_cost TEXT,
    resolution_summary TEXT,
    status TEXT
);

DROP TABLE IF EXISTS bronze_equipment;
CREATE TABLE bronze_equipment (
    equipment_id TEXT,
    customer_id TEXT,
    model TEXT,
    serial_number TEXT,
    install_date TEXT,
    capacity_kw TEXT,
    voltage TEXT,
    warranty_expiration TEXT,
    status TEXT,
    location_notes TEXT
);

DROP TABLE IF EXISTS bronze_parts;
CREATE TABLE bronze_parts (
    part_id TEXT,
    part_name TEXT,
    category TEXT,
    manufacturer TEXT,
    supplier TEXT,
    unit_cost TEXT,
    unit_price TEXT,
    stock_quantity TEXT,
    reorder_level TEXT
);

DROP TABLE IF EXISTS bronze_warranty_claims;
CREATE TABLE bronze_warranty_claims (
    claim_id TEXT,
    equipment_id TEXT,
    dispatch_id TEXT,
    part_id TEXT,
    claim_date TEXT,
    claim_amount TEXT,
    approved_amount TEXT,
    status TEXT,
    denial_reason TEXT,
    claim_notes TEXT
);
