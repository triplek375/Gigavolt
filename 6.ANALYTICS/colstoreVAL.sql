# =======================================================================
# VALIDATING SPEED BENEFITS OF COLUMNSTORE OVER INNODB
# =======================================================================
USE gigavolt_db;

-- InnoDB Execution Speed
SELECT SQL_NO_CACHE 
     service_type_id, 
     COUNT(dispatch_id) AS total_dispatches, 
     SUM(labor_cost) AS total_labor_cost, 
     AVG(hours_spent) AS average_hours 
FROM dispatches 
GROUP BY service_type_id 
ORDER BY total_labor_cost DESC;

-- ColumnStore Execution Speed
SELECT SQL_NO_CACHE 
     service_type_id, 
     COUNT(dispatch_id) AS total_dispatches, 
     SUM(labor_cost) AS total_labor_cost, 
     AVG(hours_spent) AS average_hours 
FROM dispatches_cs 
GROUP BY service_type_id 
ORDER BY total_labor_cost DESC;