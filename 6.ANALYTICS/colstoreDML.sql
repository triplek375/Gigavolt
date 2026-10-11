# =======================================================================
# INSERT DATA INTO OLAP TABLE
# =======================================================================
USE gigavolt_db;

INSERT INTO dispatches_cs 
SELECT * FROM dispatches;