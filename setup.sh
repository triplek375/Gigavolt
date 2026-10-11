#!/bin/bash

# =======================================================================
# (All) Galera Setup and Stop mariadb service
# (Primary) Bootstrapping Cluster and Waiting for other nodes
# (All) Start mariadb service
# (Primary) Data Loading, Processing and Validation
# Usage : bash /opt/scripts/2_galera.sh primary
# =======================================================================

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Galera Setup..."
echo "==================================================================="

read -p "Enter IP addresses for all nodes : " ip_addresses

sed -i 's/^#wsrep_cluster_name.*/wsrep_cluster_name="Galera Cluster"/' /etc/mysql/mariadb.conf.d/60-galera.cnf
sed -i "s|^#wsrep_cluster_address.*|wsrep_cluster_address=\"gcomm://$ip_addresses\"|" /etc/mysql/mariadb.conf.d/60-galera.cnf
sed -i 's/^#wsrep_on.*/wsrep_on=ON/' /etc/mysql/mariadb.conf.d/60-galera.cnf
sed -i 's/^#innodb_flush_log_at_trx_commit.*/innodb_flush_log_at_trx_commit=0/' /etc/mysql/mariadb.conf.d/60-galera.cnf
sed -i 's/^#wsrep_slave_threads.*/wsrep_slave_threads=4/' /etc/mysql/mariadb.conf.d/60-galera.cnf

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Stopping mariadb service..."
echo "==================================================================="

systemctl stop mariadb

if [[ "$1" == "primary" ]]; then
    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] (Primary) Bootstrapping Cluster..."
    echo "==================================================================="

    sudo galera_new_cluster
    
    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] PAUSED: Waiting for other nodes..."
    echo "==================================================================="
    
    EXPECTED_NODES = $(echo "$ip_addresses" | awk -F, '{print NF}')
    while true; do
        CLUSTER_SIZE=$(mariadb -N -e "SHOW GLOBAL STATUS LIKE 'wsrep_cluster_size';" | awk '{print $2}')
        
        if [[ "$CLUSTER_SIZE" -ge "$EXPECTED_NODES" ]]; then
            echo "Success! Cluster size is $CLUSTER_SIZE."

            echo "==================================================================="
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting mariadb service..."
            echo "==================================================================="

            systemctl start mariadb

            echo "==================================================================="
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Galera Setup Successful!"
            echo "==================================================================="
            
            break
        fi
        
        echo "Current cluster size: ${CLUSTER_SIZE:-0}/$EXPECTED_NODES. Waiting 10 seconds..."
        sleep 10
    done
else
    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] (Other) Joining existing Cluster..."
    echo "==================================================================="

    systemctl start mariadb
    
    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Galera Setup Successful! Exiting..."
    echo "==================================================================="
    
    exit 0
fi

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