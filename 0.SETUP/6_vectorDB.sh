#!/bin/bash

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Python venv and dependencies setup..."
echo "==================================================================="
apt-get install -y python3-venv python3-pip
# Route pip temp operations to EBS disk (/var/tmp) instead of RAM tmpfs (/tmp)
export TMPDIR=/var/tmp

python3 -m venv /opt/vector_env
source /opt/vector_env/bin/activate
/opt/vector_env/bin/pip install --no-cache-dir --upgrade pip

# Install lightweight CPU-only PyTorch first with no wheel caching
/opt/vector_env/bin/pip install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/cpu

# Install remaining lab dependencies
/opt/vector_env/bin/pip install --no-cache-dir pymysql sqlalchemy pandas PyPDF2 chromadb sentence-transformers

# # 1. Create a 2GB swap file
# fallocate -l 2G /swapfile

# # 2. Secure permissions
# chmod 600 /swapfile

# # 3. Format and enable swap
# mkswap /swapfile
# swapon /swapfile

# # 4. Verify swap is active
# free -h