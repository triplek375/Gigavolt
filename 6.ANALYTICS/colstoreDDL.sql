# =======================================================================
# DEFINE OLAP TABLES
# =======================================================================
USE gigavolt_db;

-- Create the InnoDB analytical table
CREATE TABLE dispatches_analytics_innodb ENGINE=InnoDB AS
SELECT 
    d.dispatch_id, 
    d.dispatch_date, 
    s.service_type_name, 
    d.hours_spent, 
    d.labor_cost
FROM dispatches d
JOIN serviceTypes s ON d.service_type_id = s.service_type_id;

-- Create the ColumnStore equivalent
CREATE TABLE dispatches_analytics_cs ENGINE=ColumnStore AS
SELECT * FROM dispatches_analytics_innodb;