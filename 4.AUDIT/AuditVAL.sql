# =====================================================================
# VALIDATING TRIGGERS FOR IMMUTABILITY AND LOGGING
# =====================================================================
USE gigavolt_db;

-- 1. Perform an INSERT to fire the AFTER INSERT trigger
INSERT INTO customers (
    customer_id, first_name, last_name, company_id, phone, 
    email, address, location_id, created_date, status_id
) VALUES (
    'TEST-001', 'John', 'Doe', 1, '555-0199', 
    'jdoe@example.com', '123 Tech Lane', 1, CURRENT_DATE, 1
);

-- 2. Perform an UPDATE to fire the BEFORE UPDATE trigger
UPDATE customers 
SET 
    email = 'jdoe.updated@example.com', 
    status_id = 2 
WHERE customer_id = 'TEST-001';

-- 3. Attempt an UPDATE on the Audit_Logs table
UPDATE Audit_Logs 
SET operation_type = 'TAMPERED' 
WHERE audit_id = 1;

-- 4. Attempt a DELETE on the Audit_Logs table
DELETE FROM Audit_Logs 
WHERE audit_id = 1;

-- Query the immutable audit log to verify captured events
SELECT *
FROM Audit_Logs 
WHERE record_id = 'TEST-001' 
ORDER BY changed_at DESC \G;