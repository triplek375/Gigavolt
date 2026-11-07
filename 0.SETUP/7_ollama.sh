#!/bin/bash

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ollama Setup"
echo "==================================================================="
export HOME="${HOME:-/root}"

sudo apt update && sudo apt upgrade -y

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

systemctl start ollama

# Pull a model (e.g., llama2 or a smaller model like phi)
ollama pull phi

# Test locally
ollama run phi "Howdy, who the heck are you?"