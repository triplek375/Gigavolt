#!/bin/bash

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Downloading data files from 622.gomillion.org"
echo "==================================================================="
mkdir -p /opt/data
wget -q --show-progress "https://622.gomillion.org/data/fall2026.zip" -O /opt/data/data.zip
unzip /opt/data/data.zip -d /opt/data

mkdir -p /opt/undata
wget -q --show-progress "https://622.gomillion.org/data/UnstructuredData.zip" -O /opt/undata/UnstructuredData.zip
unzip -j /opt/undata/UnstructuredData.zip -d /opt/undata

wget -q --show-progress "https://622.gomillion.org/data/telemetry_data.json" -O /opt/undata/telemetry_data.json