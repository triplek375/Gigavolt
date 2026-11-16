-- =====================================================================
-- ADD STORED PROCEDURES FOR LLM CONTEXT & PROVENANCE STORE
-- =====================================================================
USE gigavolt_db;

DROP TABLE IF EXISTS rag_payloads;
CREATE TABLE rag_payloads (
    payload_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    record_id VARCHAR(100) NOT NULL,
    context_type VARCHAR(50) NOT NULL,
    payload_text LONGTEXT NOT NULL,
    metadata JSON NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_record_context (record_id, context_type),
    INDEX idx_context_type (context_type)
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

    START TRANSACTION;

    -- 1. Upsert Dispatch Records with Full 5-Field Provenance Metadata
    INSERT INTO rag_payloads (record_id, context_type, payload_text, metadata)
    SELECT
        d.dispatch_id,
        'DISPATCH_RECORD',
        CONCAT(
            d.service_context, 
            '. Technician: ', COALESCE(CONCAT(t.first_name, ' ', t.last_name), 'Unknown'),
            '. Service Type: ', COALESCE(st.service_type_name, 'Unknown'),
            '. Status: ', COALESCE(ds.status_name, 'Unknown')
        ),
        JSON_OBJECT(
            'database_type', 'MariaDB',
            'record_id', d.dispatch_id,
            'document_name', 'gigavolt_db.dispatches',
            'chunk_id', CONCAT('SQL_DISP_', d.dispatch_id),
            'timestamp', COALESCE(CAST(d.dispatch_date AS CHAR), CAST(CURRENT_DATE AS CHAR)),
            'equipment_id', d.equipment_id,
            'technician_name', CONCAT(t.first_name, ' ', t.last_name),
            'service_type', st.service_type_name,
            'status', ds.status_name
        )
    FROM dispatches d
    LEFT JOIN technicians t ON d.technician_id = t.technician_id
    LEFT JOIN serviceTypes st ON d.service_type_id = st.service_type_id
    LEFT JOIN dispatchStatus ds ON d.status_id = ds.status_id
    ON DUPLICATE KEY UPDATE
        payload_text = VALUES(payload_text),
        metadata = VALUES(metadata),
        updated_at = CURRENT_TIMESTAMP;

    -- 2. Upsert Warranty Claims with Full 5-Field Provenance Metadata
    INSERT INTO rag_payloads (record_id, context_type, payload_text, metadata)
    SELECT
        wc.claim_id,
        'WARRANTY_CLAIM',
        CONCAT(
            wc.claim_context,
            '. Part: ', COALESCE(p.part_name, 'None'),
            '. Status: ', COALESCE(cs.status_name, 'Unknown')
        ),
        JSON_OBJECT(
            'database_type', 'MariaDB',
            'record_id', wc.claim_id,
            'document_name', 'gigavolt_db.warrantyClaims',
            'chunk_id', CONCAT('SQL_CLM_', wc.claim_id),
            'timestamp', COALESCE(CAST(wc.claim_date AS CHAR), CAST(CURRENT_DATE AS CHAR)),
            'equipment_id', wc.equipment_id,
            'dispatch_id', wc.dispatch_id,
            'part_name', COALESCE(p.part_name, 'None'),
            'claim_status', cs.status_name
        )
    FROM warrantyClaims wc
    LEFT JOIN parts p ON wc.part_id = p.part_id
    LEFT JOIN claimStatus cs ON wc.status_id = cs.status_id
    ON DUPLICATE KEY UPDATE
        payload_text = VALUES(payload_text),
        metadata = VALUES(metadata),
        updated_at = CURRENT_TIMESTAMP;

    -- 3. Upsert Equipment Profiles with Full 5-Field Provenance Metadata
    INSERT INTO rag_payloads (record_id, context_type, payload_text, metadata)
    SELECT
        CONCAT(e.equipment_id, '_', e.status_id),
        'EQUIPMENT_PROFILE',
        CONCAT(
            e.equipment_context,
            '. Customer: ', COALESCE(CONCAT(c.first_name, ' ', c.last_name), 'Unknown'),
            '. Model: ', COALESCE(em.model_name, 'Unknown'),
            ' (', COALESCE(em.capacity_kw, 0), 'kW, ', COALESCE(em.voltage, 0), 'V)',
            '. Status: ', COALESCE(es.status_name, 'Unknown')
        ),
        JSON_OBJECT(
            'database_type', 'MariaDB',
            'record_id', e.equipment_id,
            'document_name', 'gigavolt_db.equipment',
            'chunk_id', CONCAT('SQL_EQ_', e.equipment_id),
            'timestamp', COALESCE(CAST(e.install_date AS CHAR), CAST(CURRENT_DATE AS CHAR)),
            'equipment_id', e.equipment_id,
            'serial_number', e.serial_number,
            'customer_name', CONCAT(c.first_name, ' ', c.last_name),
            'model_name', em.model_name,
            'equipment_status', es.status_name
        )
    FROM equipment e
    LEFT JOIN customers c ON e.customer_id = c.customer_id
    LEFT JOIN equipmentModels em ON e.model_id = em.model_id
    LEFT JOIN equipmentStatus es ON e.status_id = es.status_id
    ON DUPLICATE KEY UPDATE
        payload_text = VALUES(payload_text),
        metadata = VALUES(metadata),
        updated_at = CURRENT_TIMESTAMP;

    COMMIT;
END //

DELIMITER ;