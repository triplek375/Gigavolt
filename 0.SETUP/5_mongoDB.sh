#!/bin/bash

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Adding MongoDB community repository..."
echo "==================================================================="

curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list

# Update your local package database and install the MongoDB packages:

sudo apt-get update
sudo apt-get install -y mongodb-org

# Start the MongoDB service and enable it to start automatically on reboot:

sudo systemctl start mongod
sudo systemctl enable mongod

# Install remaining lab dependencies
/opt/venv/bin/pip install --no-cache-dir pymongo