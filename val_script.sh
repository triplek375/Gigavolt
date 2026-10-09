#!/bin/bash

# =======================================================================
# Data Validation Script
# =======================================================================

# Log all output (stdout & stderr) to a custom logfile
LOGFILE="/var/log/data-val.log"
exec > >(tee -a "${LOGFILE}") 2>&1

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
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Data Validation Successful!"
echo "==================================================================="