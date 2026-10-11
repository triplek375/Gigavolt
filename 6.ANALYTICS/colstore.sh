#!/bin/bash

# =======================================================================
# Columnstore Setup and Performance Validation
# Usage : bash /opt/scripts/colstore.sh
# =======================================================================

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running DDL Script for ColumnStore"
echo "==================================================================="

mariadb < /opt/scripts/colstoreDDL.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ColumnStore Speed Validation"
echo "==================================================================="

mariadb < /opt/scripts/colstoreVAL.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Validation Complete!"
echo "==================================================================="