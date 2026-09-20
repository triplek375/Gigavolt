-- =====================================================================
-- DEFINE VIEWS FOR TECHNICIAN
-- =====================================================================
USE gigavolt_db;

-- View that restricts access to sensitive information
CREATE OR REPLACE VIEW vw_customers_operational AS
SELECT 
    customer_id,
    first_name,
    last_name,
    company_id,
    '***-***-****' AS phone,          -- Masked sensitive data
    '****@****.***' AS email,         -- Masked sensitive data
    location_id,
    created_date,
    status_id
FROM customers;

-- Define technician role
CREATE ROLE IF NOT EXISTS 'technician';

-- Grant SELECT permissions ONLY on the view
GRANT SELECT ON gigavolt_db.vw_customers_operational TO 'technician';

-- Revoke any direct access to the base customers table just to be safe
REVOKE ALL PRIVILEGES ON gigavolt_db.customers FROM 'technician';

-- Create a test user
CREATE USER IF NOT EXISTS 'tech_user'@'localhost' IDENTIFIED BY 'SecurePass123!';
GRANT 'technician' TO 'tech_user'@'localhost';
SET DEFAULT ROLE 'technician' FOR 'tech_user'@'localhost';

FLUSH PRIVILEGES;