#!/bin/bash

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running Data Pipeline"
echo "==================================================================="

# Enable strict error handling
set -e
# Activate the Python virtual environment
source /opt/venv/bin/activate

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running Bronze Scripts"
echo "==================================================================="

mariadb < /opt/scripts/BronzeDDL.sql
mariadb < /opt/scripts/BronzeDML.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running Silver Scripts"
echo "==================================================================="

mariadb < /opt/scripts/SilverDDL.sql
python3 /opt/scripts/SilverPROCESS.py

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running Scripts for LLM Context"
echo "==================================================================="

mariadb < /opt/scripts/PayloadCOL.sql
mariadb < /opt/scripts/PayloadSP.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running Scripts for Audit Logs Setup"
echo "==================================================================="

mariadb < /opt/scripts/AuditDDL.sql
mariadb < /opt/scripts/AuditTRIG.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running Scripts for Data Security"
echo "==================================================================="

mariadb < /opt/scripts/techVW.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Creating csv file with loads of data"
echo "==================================================================="

mkdir -p /opt/data
python3 /opt/scripts/colstoreData.py

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running DDL and DML Script for ColumnStore"
echo "==================================================================="

sed -i 's/dispatches_large_cs/dispatches_cs_large/g' /opt/scripts/colstoreDDL.sql /opt/scripts/colstoreDML.sql /opt/scripts/colstoreVAL.sql
mariadb < /opt/scripts/colstoreDDL.sql
mariadb < /opt/scripts/colstoreDML.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Chunking Engine"
echo "==================================================================="

python3 /opt/scripts/chunking_engine.py --data-dir /opt/undata --chunk-size 384 --overlap 64 --output /opt/undata/gigavolt_chunks.json --stats

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Generate Embeddings"
echo "==================================================================="

python3 /opt/scripts/generate_embeddings.py --input-chunks /opt/undata/gigavolt_chunks.json --batch-size 32 --output-prefix /opt/undata/gigavolt_embeddings

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Vector Database Operations"
echo "==================================================================="

python3 /opt/scripts/vector_db.py --db-path /opt/undata/gigavolt_vectordb --populate-from-embeddings /opt/undata/gigavolt_embeddings --M 32 --ef-construction 100 --ef-search 40

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] MongoDB Scripts"
echo "==================================================================="

bash /opt/scripts/import_and_index.sh

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Data Definition and Loading Complete!"
echo "==================================================================="
