#!/bin/bash

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Adding MariaDB community repository..."
echo "==================================================================="
curl -o /etc/apt/keyrings/mariadb-keyring.asc 'https://mariadb.org/mariadb_release_signing_key.pgp'

cat << EOL > /etc/apt/sources.list.d/mariadb.sources
X-Repolib-Name: MariaDB
Types: deb
URIs: https://mirrors.accretive-networks.net/mariadb/repo/12.3/ubuntu
Suites: resolute
Components: main main/debug
Signed-By: /etc/apt/keyrings/mariadb-keyring.asc
EOL
# Refresh package lists to include the newly added repository
apt-get update -y

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Installing MariaDB server..."
echo "==================================================================="
apt-get install -y mariadb-server mariadb-client mariadb-plugin-columnstore

# Clean apt cache to free disk space immediately
apt-get clean
rm -rf /var/lib/apt/lists/*

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] MariaDB installation complete!"
echo "Service Status: $(systemctl is-active mariadb)"
echo "==================================================================="