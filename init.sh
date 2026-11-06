#!/bin/bash

# =======================================================================
# AWS EC2 User Data Script
# =======================================================================

# Enable strict error handling
set -e
# Log all output (stdout & stderr) to a custom logfile
exec > >(tee -a "/var/log/user-data.log") 2>&1

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting User Data initialization..."
echo "==================================================================="

bash /opt/scripts/0_ubuntu.sh

bash /opt/scripts/1_github.sh

bash /opt/scripts/2_data.sh

bash /opt/scripts/3_mariaDB.sh

bash /opt/scripts/4_mongoDB.sh


echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Instance Initialization Successful!"
echo "==================================================================="