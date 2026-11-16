#!/bin/bash
echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running Validation & Benchmarking"
echo "==================================================================="

# Enable strict error handling
set -e

# Activate the Python virtual environment
source /opt/venv/bin/activate

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bronze Validation"
echo "==================================================================="
mariadb < /opt/scripts/BronzeVAL.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Silver Validation"
echo "==================================================================="
mariadb < /opt/scripts/SilverVAL.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Stored Procedure & Context Store Validation"
echo "==================================================================="
mariadb < /opt/scripts/PayloadVAL.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Triggers & Audit Immutability Validation"
echo "==================================================================="
mariadb -f < /opt/scripts/AuditVAL.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ColumnStore vs InnoDB Speed Validation"
echo "==================================================================="
mariadb < /opt/scripts/colstoreVAL.sql

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Vector HNSW Latency & Parameter Tuning Benchmark"
echo "==================================================================="
python3 /opt/scripts/vector_db.py --db-path /opt/undata/gigavolt_vectordb --benchmark --tune-hnsw

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Hybrid Search Validation"
echo "==================================================================="
python3 /opt/scripts/hybridVAL.py

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Automated DAG Incremental & New Data Arrival Test"
echo "==================================================================="
# 1. Verify idempotent no-op when no files have changed
python3 /opt/scripts/pipeline_dag.py
# 2. Simulate new data arrival and verify incremental propagation across all DBs
python3 /opt/scripts/pipeline_dag.py --simulate-new-data

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 24-Prompt RAG Latency, Optimization & Provenance Suite"
echo "==================================================================="
python3 /opt/scripts/ragVAL.py --model qwen2.5:0.5b --report-out /opt/scripts/BENCHMARK_REPORT.md

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Validation & Benchmarking Complete!"
echo "==================================================================="