# =====================================================================
# ADD TRIGGERS FOR AUDIT LOGGING
# =====================================================================
USE gigavolt_db;

DELIMITER //

-- AFTER INSERT Trigger for customers
CREATE TRIGGER trg_customers_after_insert
AFTER INSERT ON customers
FOR EACH ROW
BEGIN
    INSERT INTO Audit_Logs (table_name, operation_type, record_id, old_values, new_values, changed_by)
    VALUES (
        'customers', 
        'INSERT', 
        NEW.customer_id, 
        NULL, 
        JSON_OBJECT('first_name', NEW.first_name, 'last_name', NEW.last_name, 'email', NEW.email, 'status_id', NEW.status_id),
        CURRENT_USER()
    );
END //

-- BEFORE UPDATE Trigger for customers
CREATE TRIGGER trg_customers_before_update
BEFORE UPDATE ON customers
FOR EACH ROW
BEGIN
    INSERT INTO Audit_Logs (table_name, operation_type, record_id, old_values, new_values, changed_by)
    VALUES (
        'customers', 
        'UPDATE', 
        OLD.customer_id, 
        JSON_OBJECT('first_name', OLD.first_name, 'last_name', OLD.last_name, 'email', OLD.email, 'status_id', OLD.status_id),
        JSON_OBJECT('first_name', NEW.first_name, 'last_name', NEW.last_name, 'email', NEW.email, 'status_id', NEW.status_id),
        CURRENT_USER()
    );
END //

-- AFTER INSERT Trigger for warrantyClaims
CREATE TRIGGER trg_warrantyclaims_after_insert
AFTER INSERT ON warrantyClaims
FOR EACH ROW
BEGIN
    INSERT INTO Audit_Logs (table_name, operation_type, record_id, old_values, new_values, changed_by)
    VALUES (
        'warrantyClaims', 
        'INSERT', 
        NEW.claim_id, 
        NULL, 
        JSON_OBJECT('claim_amount', NEW.claim_amount, 'approved_amount', NEW.approved_amount, 'status_id', NEW.status_id),
        CURRENT_USER()
    );
END //

-- BEFORE UPDATE Trigger for warrantyClaims
CREATE TRIGGER trg_warrantyclaims_before_update
BEFORE UPDATE ON warrantyClaims
FOR EACH ROW
BEGIN
    INSERT INTO Audit_Logs (table_name, operation_type, record_id, old_values, new_values, changed_by)
    VALUES (
        'warrantyClaims', 
        'UPDATE', 
        OLD.claim_id, 
        JSON_OBJECT('claim_amount', OLD.claim_amount, 'approved_amount', OLD.approved_amount, 'status_id', OLD.status_id, 'denial_reason', OLD.denial_reason),
        JSON_OBJECT('claim_amount', NEW.claim_amount, 'approved_amount', NEW.approved_amount, 'status_id', NEW.status_id, 'denial_reason', NEW.denial_reason),
        CURRENT_USER()
    );
END //

-- AFTER INSERT Trigger for dispatches
CREATE TRIGGER trg_dispatches_after_insert
AFTER INSERT ON dispatches
FOR EACH ROW
BEGIN
    INSERT INTO Audit_Logs (table_name, operation_type, record_id, old_values, new_values, changed_by)
    VALUES (
        'dispatches', 
        'INSERT', 
        NEW.dispatch_id, 
        NULL, 
        JSON_OBJECT('technician_id', NEW.technician_id, 'hours_spent', NEW.hours_spent, 'labor_cost', NEW.labor_cost, 'status_id', NEW.status_id),
        CURRENT_USER()
    );
END //

-- BEFORE UPDATE Trigger for dispatches
CREATE TRIGGER trg_dispatches_before_update
BEFORE UPDATE ON dispatches
FOR EACH ROW
BEGIN
    INSERT INTO Audit_Logs (table_name, operation_type, record_id, old_values, new_values, changed_by)
    VALUES (
        'dispatches', 
        'UPDATE', 
        OLD.dispatch_id, 
        JSON_OBJECT('technician_id', OLD.technician_id, 'hours_spent', OLD.hours_spent, 'labor_cost', OLD.labor_cost, 'status_id', OLD.status_id),
        JSON_OBJECT('technician_id', NEW.technician_id, 'hours_spent', NEW.hours_spent, 'labor_cost', NEW.labor_cost, 'status_id', NEW.status_id),
        CURRENT_USER()
    );
END //

DELIMITER ;