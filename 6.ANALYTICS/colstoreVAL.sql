# =======================================================================
# VALIDATING SPEED BENEFITS OF COLUMNSTORE OVER INNODB
# =======================================================================
USE gigavolt_db;

-- 1. InnoDB Execution Test
SET @start_innodb = SYSDATE(6);

SELECT SQL_NO_CACHE 
     SUM(POWER(labor_cost, 2)) AS sum_of_squares,
     STDDEV_POP(labor_cost) AS standard_deviation,
     VARIANCE(labor_cost) AS variance
FROM dispatches_large_innodb;

SET @end_innodb = SYSDATE(6);
SET @time_innodb = TIMESTAMPDIFF(MICROSECOND, @start_innodb, @end_innodb) / 1000000.0;

-- 2. ColumnStore Execution Test
SET @start_cs = SYSDATE(6);

SELECT SQL_NO_CACHE 
     SUM(POWER(labor_cost, 2)) AS sum_of_squares,
     STDDEV_POP(labor_cost) AS standard_deviation,
     VARIANCE(labor_cost) AS variance
FROM dispatches_cs_large;

SET @end_cs = SYSDATE(6);
SET @time_cs = TIMESTAMPDIFF(MICROSECOND, @start_cs, @end_cs) / 1000000.0;

-- 3. Display Labeled Comparison
SELECT 
    CONCAT(@time_innodb, ' seconds') AS InnoDB_Execution_Time,
    CONCAT(@time_cs, ' seconds') AS ColumnStore_Execution_Time,
    CONCAT(ROUND(@time_innodb - @time_cs, 4), ' seconds') AS Time_Saved_By_ColumnStore;