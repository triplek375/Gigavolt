-- =====================================================================
-- RELATIONAL INDEX TUNING & INCREMENTAL METADATA
-- =====================================================================
USE gigavolt_db;

-- 1. Add last_updated timestamps for incremental tracking & provenance
ALTER TABLE customers 
    ADD COLUMN IF NOT EXISTS last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

ALTER TABLE equipment 
    ADD COLUMN IF NOT EXISTS last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

ALTER TABLE dispatches 
    ADD COLUMN IF NOT EXISTS last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

ALTER TABLE parts 
    ADD COLUMN IF NOT EXISTS last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

ALTER TABLE warrantyClaims 
    ADD COLUMN IF NOT EXISTS last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- 2. Secondary & Composite Indexes for Multi-Hop & Temporal RAG Queries
-- Equipment lookups by serial_number, warranty expiration range, install_date, and customer
CREATE INDEX IF NOT EXISTS idx_equipment_serial ON equipment(serial_number);
CREATE INDEX IF NOT EXISTS idx_equipment_warranty_exp ON equipment(warranty_expiration);
CREATE INDEX IF NOT EXISTS idx_equipment_install_date ON equipment(install_date);
CREATE INDEX IF NOT EXISTS idx_equipment_customer_model ON equipment(customer_id, model_id, status_id);

-- Warranty claims lookups by equipment + temporal ordering and status
CREATE INDEX IF NOT EXISTS idx_claims_eq_date ON warrantyClaims(equipment_id, claim_date DESC);
CREATE INDEX IF NOT EXISTS idx_claims_status_date ON warrantyClaims(status_id, claim_date DESC);
CREATE INDEX IF NOT EXISTS idx_claims_part ON warrantyClaims(part_id);

-- Dispatches lookups by equipment + dispatch_date for temporal service history
CREATE INDEX IF NOT EXISTS idx_dispatches_eq_date ON dispatches(equipment_id, dispatch_date DESC);
CREATE INDEX IF NOT EXISTS idx_dispatches_tech_service ON dispatches(technician_id, service_type_id);

-- Customer & Geographic hierarchy lookups
CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(last_name, first_name);
CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);
CREATE INDEX IF NOT EXISTS idx_locations_zip ON locations(zip);
CREATE INDEX IF NOT EXISTS idx_cities_name ON cities(city_name);
CREATE INDEX IF NOT EXISTS idx_states_name ON states(state_name);

-- Parts inventory & pricing lookups
CREATE INDEX IF NOT EXISTS idx_parts_name ON parts(part_name);
CREATE INDEX IF NOT EXISTS idx_parts_cat_mfg ON parts(category_id, manufacturer_id);

-- 3. Update Optimizer Statistics for Query Plan Tuning
ANALYZE TABLE 
    companies, countries, states, cities, locations, customerStatus, customers,
    equipmentModels, equipmentStatus, equipment, technicians, serviceTypes,
    dispatchStatus, dispatches, partCategories, manufacturers, suppliers,
    parts, claimStatus, warrantyClaims;