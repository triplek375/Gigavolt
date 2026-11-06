#!/bin/bash

# =======================================================================
# Galera Setup, Disable Auto Restart and Stop mariadb service
# Joining the Cluster
# =======================================================================

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Galera Setup..."
echo "==================================================================="

apt-get install -y mariadb-client mariadb-backup mariadb-common mariadb-server-galera galera-4 libmariadb3 mariadb-plugin-columnstore

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

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] (Other) Joining existing Cluster..."
echo "==================================================================="

systemctl start mariadb

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Galera Setup Complete!"
echo "==================================================================="
