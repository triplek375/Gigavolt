# =====================================================================
# IMPORT DATA INTO BRONZE TABLES
# =====================================================================
USE gigavolt_db;

LOAD DATA INFILE '/opt/data/customers.csv'
INTO TABLE bronze_customers
FIELDS TERMINATED BY ','
ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;

LOAD DATA INFILE '/opt/data/dispatches.csv'
INTO TABLE bronze_dispatches
FIELDS TERMINATED BY ','
ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;

LOAD DATA INFILE '/opt/data/equipment.csv'
INTO TABLE bronze_equipment
FIELDS TERMINATED BY ','
ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;

LOAD DATA INFILE '/opt/data/parts.csv'
INTO TABLE bronze_parts
FIELDS TERMINATED BY ','
ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;

LOAD DATA INFILE '/opt/data/warranty_claims.csv'
INTO TABLE bronze_warranty_claims
FIELDS TERMINATED BY ','
ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;