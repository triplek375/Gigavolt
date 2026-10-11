# =======================================================================
# DEFINE OLAP TABLES
# =======================================================================
USE gigavolt_db;

CREATE TABLE dispatches_analytics_innodb (
    dispatch_id VARCHAR(50),
    dispatch_date DATE,
    service_type_name VARCHAR(50),
    hours_spent DECIMAL(10,2),
    labor_cost DECIMAL(10,2)
) ENGINE=InnoDB;

CREATE TABLE dispatches_analytics_cs (
    dispatch_id VARCHAR(50),
    dispatch_date DATE,
    service_type_name VARCHAR(50),
    hours_spent DECIMAL(10,2),
    labor_cost DECIMAL(10,2)
) ENGINE=ColumnStore;
