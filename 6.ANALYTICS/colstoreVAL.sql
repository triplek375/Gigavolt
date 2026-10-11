# =======================================================================
# VALIDATING SPEED BENEFITS OF COLUMNSTORE OVER INNODB
# =======================================================================
USE gigavolt_db;

-- 1. InnoDB Execution Test
SET @start_innodb = SYSDATE(6);

SELECT SQL_NO_CACHE 
     service_type_id, 
     COUNT(dispatch_id) AS total_dispatches, 
     SUM(labor_cost) AS total_labor_cost, 
     AVG(hours_spent) AS average_hours 
FROM dispatches_large_innodb 
GROUP BY service_type_id 
ORDER BY total_labor_cost DESC;

SET @end_innodb = SYSDATE(6);
SET @time_innodb = TIMESTAMPDIFF(MICROSECOND, @start_innodb, @end_innodb) / 1000000.0;

-- 2. ColumnStore Execution Test
SET @start_cs = SYSDATE(6);

SELECT SQL_NO_CACHE 
     service_type_id, 
     COUNT(dispatch_id) AS total_dispatches, 
     SUM(labor_cost) AS total_labor_cost, 
     AVG(hours_spent) AS average_hours 
FROM dispatches_large_cs 
GROUP BY service_type_id 
ORDER BY total_labor_cost DESC;

SET @end_cs = SYSDATE(6);
SET @time_cs = TIMESTAMPDIFF(MICROSECOND, @start_cs, @end_cs) / 1000000.0;

-- 3. Display Labeled Comparison
SELECT 
    CONCAT(@time_innodb, ' seconds') AS InnoDB_Execution_Time,
    CONCAT(@time_cs, ' seconds') AS ColumnStore_Execution_Time,
    CONCAT(ROUND(@time_innodb - @time_cs, 4), ' seconds') AS Time_Saved_By_ColumnStore;