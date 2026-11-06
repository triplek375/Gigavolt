#!/bin/bash

# =======================================================================
# AWS EC2 User Data Script
# =======================================================================

# Enable strict error handling
set -e
# Log all output (stdout & stderr) to a custom logfile
exec > >(tee -a "/var/log/user-data.log") 2>&1

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Configuring non-interactive mode"
echo "==================================================================="
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
UBUNTU_CODENAME=$(lsb_release -cs)

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting User Data initialization..."
echo "==================================================================="

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
apt-get install -y apt-transport-https curl unzip

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Downloading code files from github"
echo "==================================================================="
mkdir -p /opt/scripts
wget -q --show-progress "https://github.com/triplek375/Gigavolt/archive/refs/heads/main.zip" -O /opt/scripts/Gigavolt.zip
unzip -o -j /opt/scripts/Gigavolt.zip -d /opt/scripts

bash /opt/scripts/1_data.sh

bash /opt/scripts/2_mariaDB.sh

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Instance Initialization Successful!"
echo "==================================================================="