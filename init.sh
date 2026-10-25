#!/bin/bash

# =======================================================================
# AWS EC2 User Data Script - Ubuntu 26.04
# Description: Automated unattended setup for MariaDB 12.3 with logging
# =======================================================================

# Enable strict error handling
set -e
# Log all output (stdout & stderr) to a custom logfile
exec > >(tee -a "/var/log/user-data.log") 2>&1

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting User Data initialization..."
echo "==================================================================="

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Configuring non-interactive mode"
echo "==================================================================="
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
UBUNTU_CODENAME=$(lsb_release -cs)

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Updating list of available packages"
echo "==================================================================="
apt-get update -y

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Upgrading all installed packages"
echo "==================================================================="
apt-get upgrade -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold"

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Installing prerequisites utilities for repository setup"
echo "==================================================================="
apt-get install -y apt-transport-https curl unzip python3-pip python3-venv

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Adding MariaDB community repository..."
echo "==================================================================="
curl -o /etc/apt/keyrings/mariadb-keyring.asc 'https://mariadb.org/mariadb_release_signing_key.pgp'

cat << EOL > /etc/apt/sources.list.d/mariadb.sources
# MariaDB 12.3 repository list - created 2026-08-31 12:12 UTC
# https://mariadb.org/download/
X-Repolib-Name: MariaDB
Types: deb
# deb.mariadb.org is a dynamic mirror if your preferred mirror goes offline. See https://mariadb.org/mirrorbits/ for details.
# URIs: https://deb.mariadb.org/12.3/ubuntu
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
apt-get install -y mariadb-server mariadb-client mariadb-backup mariadb-common 
apt-get install -y mariadb-server-galera galera-4 libmariadb3 mariadb-plugin-columnstore

# Clean apt cache to free disk space immediately
apt-get clean
rm -rf /var/lib/apt/lists/*

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] MariaDB installation complete!"
echo "Service Status: $(systemctl is-active mariadb)"
echo "==================================================================="

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Downloading code files from github"
echo "==================================================================="
mkdir -p /opt/scripts
wget -q --show-progress "https://github.com/triplek375/Gigavolt/archive/refs/heads/main.zip" -O /opt/scripts/Gigavolt.zip
unzip -o -j /opt/scripts/Gigavolt.zip -d /opt/scripts

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Instance Initialization Successful!"
echo "==================================================================="