#!/bin/bash

# =======================================================================
# (All) Galera Setup, Disable Auto Restart and Stop mariadb service
# (Node A) 
# - Bootstrapping Cluster and Waiting for other nodes
# - If all nodes active, then Data Loading and Processing
# - Usage : bash /opt/scripts/setup.sh primary
# (Others) 
# - Joining the Cluster
# - Usage : bash /opt/scripts/setup.sh
# =======================================================================

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Galera Setup..."
echo "==================================================================="

read -p "Enter IP addresses for all nodes : " ip_addresses

sed -i 's/^.*wsrep_cluster_name.*/wsrep_cluster_name="Galera Cluster"/' /etc/mysql/mariadb.conf.d/60-galera.cnf
sed -i "s|^.*wsrep_cluster_address.*|wsrep_cluster_address=\"gcomm://$ip_addresses\"|" /etc/mysql/mariadb.conf.d/60-galera.cnf
sed -i 's/^.*wsrep_on.*/wsrep_on=ON/' /etc/mysql/mariadb.conf.d/60-galera.cnf
sed -i 's/^.*innodb_flush_log_at_trx_commit.*/innodb_flush_log_at_trx_commit=0/' /etc/mysql/mariadb.conf.d/60-galera.cnf
sed -i 's/^.*wsrep_slave_threads.*/wsrep_slave_threads=4/' /etc/mysql/mariadb.conf.d/60-galera.cnf

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Disabling mariadb auto-restart..."
echo "==================================================================="

systemctl disable mariadb

mkdir -p /etc/systemd/system/mariadb.service.d
cat <<EOF > /etc/systemd/system/mariadb.service.d/override.conf
[Service]
Restart=no
EOF
systemctl daemon-reload

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
    
    EXPECTED_NODES=$(echo "$ip_addresses" | awk -F, '{print NF}')
    while true; do
        CLUSTER_SIZE=$(mariadb -N -e "SHOW GLOBAL STATUS LIKE 'wsrep_cluster_size';" | awk '{print $2}')
        
        if [[ "$CLUSTER_SIZE" -ge "$EXPECTED_NODES" ]]; then
            echo "Success! Cluster size is $CLUSTER_SIZE."

            echo "==================================================================="
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] Galera Setup Complete!"
            echo "==================================================================="
            
            break
        fi
        
        echo "Current cluster size: ${CLUSTER_SIZE:-0}/$EXPECTED_NODES. Waiting 10 seconds..."
        sleep 10
    done

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Downloading data files from 622.gomillion.org"
    echo "==================================================================="
    mkdir -p /opt/data
    cd /opt/data
    wget -q --show-progress "https://622.gomillion.org/data/fall2026.zip" -O data.zip
    unzip data.zip
    wget -q --show-progress "https://622.gomillion.org/data/UnstructuredData.zip" -O UnstructuredData.zip
    unzip UnstructuredData.zip

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Python venv and dependencies setup..."
    echo "==================================================================="
    # Route pip temp operations to EBS disk (/var/tmp) instead of RAM tmpfs (/tmp)
    export TMPDIR=/var/tmp
    
    python3 -m venv /opt/vector_env
    source /opt/vector_env/bin/activate
    /opt/vector_env/bin/pip install --no-cache-dir --upgrade pip

    # Install lightweight CPU-only PyTorch first with no wheel caching
    /opt/vector_env/bin/pip install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/cpu

    # Install remaining lab dependencies
    /opt/vector_env/bin/pip install --no-cache-dir pymysql sqlalchemy pandas PyPDF2 chromadb sentence-transformers

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
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Creating csv file with loads of data"
    echo "==================================================================="

    mkdir -p /opt/data
    python3 /opt/scripts/colstoreData.py

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running DDL and DML Script for ColumnStore"
    echo "==================================================================="

    sed -i 's/dispatches_large_cs/dispatches_cs_large/g' /opt/scripts/colstoreDDL.sql /opt/scripts/colstoreDML.sql /opt/scripts/colstoreVAL.sql
    mariadb < /opt/scripts/colstoreDDL.sql
    mariadb < /opt/scripts/colstoreDML.sql

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Data Definition and Loading Complete!"
    echo "==================================================================="

else
    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] (Other) Joining existing Cluster..."
    echo "==================================================================="

    systemctl start mariadb
    
    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Galera Setup Complete!"
    echo "==================================================================="

fi