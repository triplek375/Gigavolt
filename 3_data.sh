#!/bin/bash

# =======================================================================
# Data Loading, Processing and Validation Script
# Usage : bash /opt/scripts/3_data.sh
# =======================================================================

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Downloading data files from 622.gomillion.org"
echo "==================================================================="
mkdir -p /opt/data
cd /opt/data
wget -q --show-progress "https://622.gomillion.org/data/fall2026.zip" -O data.zip
unzip data.zip

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running Bronze Scripts"
echo "==================================================================="

mariadb < /opt/scripts/BronzeDDL.sql
mariadb < /opt/scripts/BronzeDML.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running Silver Scripts"
echo "==================================================================="

mariadb < /opt/scripts/SilverDDL.sql
python3 /opt/scripts/SilverPROCESS.py

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running Scripts for LLM Context"
echo "==================================================================="

mariadb < /opt/scripts/PayloadCOL.sql
mariadb < /opt/scripts/PayloadSP.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running Scripts for Audit Logs Setup"
echo "==================================================================="

mariadb < /opt/scripts/AuditDDL.sql
mariadb < /opt/scripts/AuditTRIG.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running Scripts for Data Security"
echo "==================================================================="

mariadb < /opt/scripts/techVW.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Load Data Successful!"
echo "==================================================================="


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