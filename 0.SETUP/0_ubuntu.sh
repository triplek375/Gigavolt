#!/bin/bash

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

# 1. Create a 2GB swap file
fallocate -l 2G /swapfile

# 2. Secure permissions
chmod 600 /swapfile

# 3. Format and enable swap
mkswap /swapfile
swapon /swapfile

# 4. Verify swap is active
free -h