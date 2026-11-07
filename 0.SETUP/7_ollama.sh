#!/bin/bash

echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Configuring non-interactive mode"
echo "==================================================================="
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
export HOME="${HOME:-/root}"

# Install Ollama on the Server
sudo apt update && sudo apt upgrade -y

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model (e.g., llama2 or a smaller model like phi)
ollama pull phi

# Test locally
ollama run phi "Howdy, who the heck are you?"