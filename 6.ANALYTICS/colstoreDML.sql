# =======================================================================
# INSERT DATA INTO OLAP TABLES
# =======================================================================
USE gigavolt_db;

INSERT INTO dispatches_analytics_innodb
SELECT 
     d.dispatch_id,
     d.dispatch_date,
     s.service_type_name,
     d.hours_spent,
     d.labor_cost
FROM dispatches d
JOIN serviceTypes s ON d.service_type_id = s.service_type_id;

INSERT INTO dispatches_analytics_cs
SELECT * FROM dispatches_analytics_innodb;