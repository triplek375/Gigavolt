#!/bin/bash
echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ollama Setup & Performance Tuning"
echo "==================================================================="

sudo apt-get update -y

# Install Ollama if not already installed
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
fi

# Configure systemd override to keep model loaded in RAM and support parallel queries
sudo mkdir -p /etc/systemd/system/ollama.service.d
cat << 'EOF' | sudo tee /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_KEEP_ALIVE=24h"
Environment="OLLAMA_NUM_PARALLEL=4"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_HOST=0.0.0.0:11434"
Restart=always
RestartSec=3
EOF

sudo systemctl daemon-reload
sudo systemctl enable ollama
sudo systemctl restart ollama

export HOME="${HOME:-/root}"

# Wait for Ollama HTTP API to become ready
echo "Waiting for Ollama service to listen on port 11434..."
for i in {1..15}; do
    if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "Ollama daemon is online."
        break
    fi
    sleep 2
done

# Pull phi model and pre-warm into memory with 24h keep_alive
ollama pull phi
curl -s http://localhost:11434/api/generate -d '{
  "model": "phi",
  "prompt": "System check: respond OK.",
  "stream": false,
  "keep_alive": "24h",
  "options": {"num_predict": 5, "num_ctx": 1024}
}' >/dev/null

echo "Testing Ollama API ping..."
curl -s http://localhost:11434/api/tags | grep -q "models" && echo "Ollama server is active and pre-warmed." || echo "Ollama starting..."