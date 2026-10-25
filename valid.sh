#!/bin/bash

# =======================================================================
# Data Validation
# Usage : bash /opt/scripts/valid.sh
# Usage : bash /opt/scripts/valid.sh vector
# =======================================================================

# Enable strict error handling
set -e
# Activate the Python virtual environment
source /opt/vector_env/bin/activate

if [[ "$1" == "vector" ]]; then
    # 1. Create a 2GB swap file
    fallocate -l 2G /swapfile

    # 2. Secure permissions
    chmod 600 /swapfile

    # 3. Format and enable swap
    mkswap /swapfile
    swapon /swapfile

    # 4. Verify swap is active
    free -h

    python3 /opt/scripts/pdfChunking.py
    
else
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
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ColumnStore Speed Validation"
    echo "==================================================================="

    mariadb < /opt/scripts/colstoreVAL.sql

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Validation Complete!"
    echo "==================================================================="
fi