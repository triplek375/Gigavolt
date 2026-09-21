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

-- Define tech_role role
CREATE ROLE IF NOT EXISTS 'tech_role';

-- Grant SELECT permissions ONLY on the view
GRANT SELECT ON gigavolt_db.vw_customers_operational TO 'tech_role';

-- Create a test user
CREATE USER IF NOT EXISTS 'tech_user'@'localhost' IDENTIFIED BY 'password';
GRANT 'tech_role' TO 'tech_user'@'localhost';
SET DEFAULT ROLE 'tech_role' FOR 'tech_user'@'localhost';

FLUSH PRIVILEGES;