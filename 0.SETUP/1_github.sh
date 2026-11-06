#!/bin/bash

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Downloading code files from github"
echo "==================================================================="
mkdir -p /opt/scripts
wget -q --show-progress "https://github.com/triplek375/Gigavolt/archive/refs/heads/main.zip" -O /opt/scripts/Gigavolt.zip
unzip -o -j /opt/scripts/Gigavolt.zip -d /opt/scripts