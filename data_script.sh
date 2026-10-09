#!/bin/bash

# =======================================================================
# Data Loading Script
# =======================================================================

# Log all output (stdout & stderr) to a custom logfile
LOGFILE="/var/log/data-load.log"
exec > >(tee -a "${LOGFILE}") 2>&1

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Downloading data files from 622.gomillion.org"
echo "==================================================================="
mkdir -p /opt/data
cd /opt/data
wget -q --show-progress "https://622.gomillion.org/data/fall2026.zip" -O data.zip
unzip data.zip

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Downloading SQL scripts from github"
echo "==================================================================="
mkdir -p /opt/scripts
cd /opt/scripts
wget -q --show-progress "https://github.com/triplek375/Gigavolt/archive/refs/heads/main.zip" -O Gigavolt.zip
unzip -j Gigavolt.zip

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