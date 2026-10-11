# =======================================================================
# VALIDATING SPEED BENEFITS OF COLUMNSTORE OVER INNODB
# =======================================================================

# SQL_NO_CACHE 
# Ensures we measure actual performance rather than retrieving a cached result

-- InnoDB Execution Speed
SELECT SQL_NO_CACHE 
    service_type_name, 
    COUNT(dispatch_id) AS total_dispatches, 
    SUM(labor_cost) AS total_labor_cost, 
    AVG(hours_spent) AS average_hours
FROM dispatches_analytics_innodb
GROUP BY service_type_name
ORDER BY total_labor_cost DESC;

-- ColumnStore Execution Speed
SELECT SQL_NO_CACHE 
    service_type_name, 
    COUNT(dispatch_id) AS total_dispatches, 
    SUM(labor_cost) AS total_labor_cost, 
    AVG(hours_spent) AS average_hours
FROM dispatches_analytics_cs
GROUP BY service_type_name
ORDER BY total_labor_cost DESC;