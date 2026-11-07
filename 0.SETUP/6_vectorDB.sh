#!/bin/bash

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Python venv and dependencies setup..."
echo "==================================================================="

# Install lightweight CPU-only PyTorch first with no wheel caching
/opt/venv/bin/pip install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/cpu

# Install remaining lab dependencies
/opt/venv/bin/pip install --no-cache-dir pymysql sqlalchemy pandas PyPDF2 chromadb sentence-transformers
