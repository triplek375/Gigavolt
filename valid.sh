#!/bin/bash

# =======================================================================
# Data Validation
# =======================================================================

if [[ "$1" == "columnStore" ]]; then
    # Usage : bash /opt/scripts/valid.sh columnStore (only on node 3)

    mkdir -p /opt/data
    
    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Creating csv file with loads of data"
    echo "==================================================================="

    python3 /opt/scripts/colstoreData.py

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running DDL and DML Script for ColumnStore"
    echo "==================================================================="

    mariadb < /opt/scripts/colstoreDDL.sql
    mariadb < /opt/scripts/colstoreDML.sql

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ColumnStore Speed Validation"
    echo "==================================================================="

    mariadb < /opt/scripts/colstoreVAL.sql

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Validation Complete!"
    echo "==================================================================="
else
    # Usage : bash /opt/scripts/valid.sh

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bronze Validation"
    echo "==================================================================="

    mariadb < /opt/scripts/BronzeVAL.sql

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Silver Validation"
    echo "==================================================================="

    mariadb < /opt/scripts/SilverVAL.sql

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Stored Procedure Validation"
    echo "==================================================================="

    mariadb < /opt/scripts/PayloadVAL.sql

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Triggers Validation"
    echo "==================================================================="

    mariadb -f < /opt/scripts/AuditVAL.sql

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Views Validation for tech_user"
    echo "==================================================================="

    mariadb -u tech_user -p < /opt/scripts/techVAL.sql

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Validation Complete!"
    echo "==================================================================="
fi