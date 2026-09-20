# =====================================================================
# ADD STORED PROCEDURES FOR LLM CONTEXT
# =====================================================================
USE gigavolt_db;

DROP TABLE IF EXISTS rag_payloads;
CREATE TABLE rag_payloads (
    payload_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    context_type VARCHAR(50) NOT NULL,
    payload_text LONGTEXT NOT NULL,
    metadata JSON NOT NULL
);

DELIMITER //

DROP PROCEDURE IF EXISTS sp_Prepare_RAG_Payloads//

CREATE PROCEDURE sp_Prepare_RAG_Payloads ()
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'RAG Payload generation failed. Transaction rolled back.';
    END;

    TRUNCATE TABLE rag_payloads;

    START TRANSACTION;

    INSERT INTO rag_payloads (context_type, payload_text, metadata)
    SELECT
        'DISPATCH_RECORD',
        CONCAT(
            d.service_context, 
            '. Technician: ', COALESCE(CONCAT(t.first_name, ' ', t.last_name), 'Unknown'),
            '. Service Type: ', COALESCE(st.service_type_name, 'Unknown'),
            '. Status: ', COALESCE(ds.status_name, 'Unknown')
        ),
        JSON_OBJECT(
            'dispatch_id', d.dispatch_id,
            'equipment_id', d.equipment_id,
            'technician_name', CONCAT(t.first_name, ' ', t.last_name),
            'service_type', st.service_type_name,
            'status', ds.status_name
        )
    FROM dispatches d
    LEFT JOIN technicians t ON d.technician_id = t.technician_id
    LEFT JOIN serviceTypes st ON d.service_type_id = st.service_type_id
    LEFT JOIN dispatchStatus ds ON d.status_id = ds.status_id;

    INSERT INTO rag_payloads (context_type, payload_text, metadata)
    SELECT
        'WARRANTY_CLAIM',
        CONCAT(
            wc.claim_context,
            '. Part: ', COALESCE(p.part_name, 'None'),
            '. Status: ', COALESCE(cs.status_name, 'Unknown')
        ),
        JSON_OBJECT(
            'claim_id', wc.claim_id,
            'equipment_id', wc.equipment_id,
            'dispatch_id', wc.dispatch_id,
            'part_name', COALESCE(p.part_name, 'None'),
            'claim_status', cs.status_name
        )
    FROM warrantyClaims wc
    LEFT JOIN parts p ON wc.part_id = p.part_id
    LEFT JOIN claimStatus cs ON wc.status_id = cs.status_id;

    INSERT INTO rag_payloads (context_type, payload_text, metadata)
    SELECT
        'EQUIPMENT_PROFILE',
        CONCAT(
            e.equipment_context,
            '. Customer: ', COALESCE(CONCAT(c.first_name, ' ', c.last_name), 'Unknown'),
            '. Model: ', COALESCE(em.model_name, 'Unknown'),
            ' (', COALESCE(em.capacity_kw, 0), 'kW, ', COALESCE(em.voltage, 0), 'V)',
            '. Status: ', COALESCE(es.status_name, 'Unknown')
        ),
        JSON_OBJECT(
            'equipment_id', e.equipment_id,
            'customer_name', CONCAT(c.first_name, ' ', c.last_name),
            'model_name', em.model_name,
            'equipment_status', es.status_name
        )
    FROM equipment e
    LEFT JOIN customers c ON e.customer_id = c.customer_id
    LEFT JOIN equipmentModels em ON e.model_id = em.model_id
    LEFT JOIN equipmentStatus es ON e.status_id = es.status_id;

    COMMIT;

END //

DELIMITER ;

CALL sp_Prepare_RAG_Payloads();