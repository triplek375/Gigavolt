#!/bin/bash

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ollama Setup"
echo "==================================================================="

sudo apt update && sudo apt upgrade -y

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

systemctl start ollama
systemctl enable ollama

export HOME="${HOME:-/root}"

# Pull a model (e.g., llama2 or a smaller model like phi)
ollama pull phi

# Test locally
ollama run phi "Howdy, who the heck are you?"

systemctl status ollama --no-pager || systemctl start ollama

echo "Testing Ollama API ping..."
curl -s http://localhost:11434/api/tags | grep -q "models" && echo "Ollama server is active and responding." || echo "Ollama starting..."
