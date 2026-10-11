#!/bin/bash

# =======================================================================
# Galera Setup for MariaDB Cluster
# Usage : bash /opt/scripts/2_galera.sh
# =======================================================================

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Configuring Galera Settings..."
echo "==================================================================="

read -p "Enter IP addresses for all nodes : " ip_addresses

sed -i 's/^#wsrep_cluster_name.*/wsrep_cluster_name="Galera Cluster"/' /etc/mysql/mariadb.conf.d/60-galera.cnf
sed -i "s|^#wsrep_cluster_address.*|wsrep_cluster_address=\"gcomm://$ip_addresses\"|" /etc/mysql/mariadb.conf.d/60-galera.cnf
sed -i 's/^#wsrep_on.*/wsrep_on=ON/' /etc/mysql/mariadb.conf.d/60-galera.cnf
sed -i 's/^#innodb_flush_log_at_trx_commit.*/innodb_flush_log_at_trx_commit=0/' /etc/mysql/mariadb.conf.d/60-galera.cnf
sed -i 's/^#wsrep_slave_threads.*/wsrep_slave_threads=4/' /etc/mysql/mariadb.conf.d/60-galera.cnf

if [[ "$HOSTNAME" == *A ]]; then
    echo "Current node ends with A"
    sudo galera_new_cluster
fi

systemctl start mariadb

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Galera Setup Successful!"
echo "==================================================================="