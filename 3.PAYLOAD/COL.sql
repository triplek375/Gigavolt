# =====================================================================
# ADD GENERATED COLUMNS FOR LLM CONTEXT
# =====================================================================
USE gigavolt_db;

ALTER TABLE dispatches
ADD COLUMN service_context TEXT GENERATED ALWAYS AS (
    CONCAT_WS('. ',
        CONCAT('Dispatch Date: ', IFNULL(dispatch_date, 'UNKNOWN')),
        CONCAT('Hours Spent: ', IFNULL(hours_spent, '0')),
        CONCAT('Labor Cost: $', IFNULL(labor_cost, '0.00')),
        CONCAT('Resolution: ', IFNULL(resolution_summary, 'None'))
    )
) VIRTUAL;

ALTER TABLE warrantyClaims
ADD COLUMN claim_context TEXT GENERATED ALWAYS AS (
    CONCAT_WS('. ',
        CONCAT('Claim Date: ', IFNULL(claim_date, 'UNKNOWN')),
        CONCAT('Claim Amount: $', IFNULL(claim_amount, '0.00')),
        CONCAT('Approved Amount: $', IFNULL(approved_amount, '0.00')),
        CONCAT('Notes: ', IFNULL(claim_notes, 'None')),
        CONCAT('Denial Reason: ', IFNULL(denial_reason, 'N/A'))
    )
) VIRTUAL;

ALTER TABLE equipment
ADD COLUMN equipment_context TEXT GENERATED ALWAYS AS (
    CONCAT_WS('. ',
        CONCAT('SN: ', IFNULL(serial_number, 'UNKNOWN')),
        CONCAT('Installed: ', IFNULL(install_date, 'N/A')),
        CONCAT('Warranty Expires: ', IFNULL(warranty_expiration, 'N/A')),
        CONCAT('Location Notes: ', IFNULL(location_notes, 'None'))
    )
) VIRTUAL;
