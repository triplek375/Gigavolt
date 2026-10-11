# =======================================================================
# DEFINE OLAP TABLE
# =======================================================================
USE gigavolt_db;

DROP TABLE IF EXISTS dispatches_cs;

CREATE TABLE dispatches_cs (
    dispatch_id VARCHAR(50),
    equipment_id VARCHAR(50),
    dispatch_date DATE,
    technician_id INT,
    service_type_id INT,
    hours_spent DECIMAL(10,2),
    labor_cost DECIMAL(10,2),
    resolution_summary TEXT,
    status_id INT
) ENGINE=ColumnStore;
