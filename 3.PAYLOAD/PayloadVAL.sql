# =====================================================================
# VALIDATING STORED PROCEDURE
# =====================================================================
USE gigavolt_db;

CALL sp_Prepare_RAG_Payloads();

SELECT *
FROM rag_payloads 
ORDER BY payload_id DESC 
LIMIT 5;