# =====================================================================
# DEFINE AUDIT LOGS TABLE
# =====================================================================
USE gigavolt_db;

DROP TABLE IF EXISTS Audit_Logs;

CREATE TABLE Audit_Logs (
    audit_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,
    operation_type VARCHAR(10) NOT NULL,
    record_id VARCHAR(50) NOT NULL,
    old_values JSON,
    new_values JSON,
    changed_by VARCHAR(50) NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);