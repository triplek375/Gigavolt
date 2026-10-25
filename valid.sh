#!/bin/bash

# =======================================================================
# Data Validation
# Usage : bash /opt/scripts/valid.sh
# Usage : bash /opt/scripts/valid.sh vector
# =======================================================================

# Enable strict error handling
set -e
# Activate the Python virtual environment
source /opt/vector_env/bin/activate

if [[ "$1" == "vector" ]]; then
    python3 /opt/scripts/chunking_engine.py --data-dir /opt/undata --chunk-size 384 --overlap 64 --output /opt/undata/gigavolt_chunks.json --stats
    
    python3 /opt/scripts/generate_embeddings.py --input-chunks /opt/undata/gigavolt_chunks.json --batch-size 32 --output-prefix /opt/undata/gigavolt_embeddings
    
    # Ingest precomputed embeddings into ChromaDB
    python3 /opt/scripts/vector_db.py --db-path /opt/undata/gigavolt_vectordb --populate-from-embeddings /opt/undata/gigavolt_embeddings --M 32 --ef-construction 100 --ef-search 40
    
    # Run latency benchmark SLA test
    python3 /opt/scripts/vector_db.py --db-path /opt/undata/gigavolt_vectordb --benchmark

else
    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bronze Validation"
    echo "==================================================================="

    mariadb < /opt/scripts/BronzeVAL.sql

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Silver Validation"
    echo "==================================================================="

    mariadb < /opt/scripts/SilverVAL.sql

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Stored Procedure Validation"
    echo "==================================================================="

    mariadb < /opt/scripts/PayloadVAL.sql

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Triggers Validation"
    echo "==================================================================="

    mariadb -f < /opt/scripts/AuditVAL.sql

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Views Validation for tech_user"
    echo "==================================================================="

    mariadb -u tech_user -p < /opt/scripts/techVAL.sql

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ColumnStore Speed Validation"
    echo "==================================================================="

    mariadb < /opt/scripts/colstoreVAL.sql

    echo "==================================================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Validation Complete!"
    echo "==================================================================="
fi