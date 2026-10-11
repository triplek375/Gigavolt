# =======================================================================
# INSERT DATA INTO OLAP TABLE
# =======================================================================
USE gigavolt_db;

INSERT INTO dispatches_cs (
    dispatch_id, 
    equipment_id, 
    dispatch_date, 
    technician_id, 
    service_type_id, 
    hours_spent, 
    labor_cost, 
    resolution_summary, 
    status_id
)
SELECT 
    dispatch_id, 
    equipment_id, 
    dispatch_date, 
    technician_id, 
    service_type_id, 
    hours_spent, 
    labor_cost, 
    resolution_summary, 
    status_id 
FROM dispatches;