# =======================================================================
# IMPORT LARGE DATASET INTO OLAP TABLES
# =======================================================================
USE gigavolt_db;

LOAD DATA INFILE '/opt/data/large_dispatches.csv'
INTO TABLE dispatches_large_innodb
FIELDS TERMINATED BY ','
LINES TERMINATED BY '\n'
(dispatch_id, equipment_id, dispatch_date, technician_id, service_type_id, hours_spent, labor_cost, resolution_summary, status_id);

LOAD DATA INFILE '/opt/data/large_dispatches.csv'
INTO TABLE dispatches_large_cs
FIELDS TERMINATED BY ','
LINES TERMINATED BY '\n'
(dispatch_id, equipment_id, dispatch_date, technician_id, service_type_id, hours_spent, labor_cost, resolution_summary, status_id);