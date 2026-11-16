#!/bin/bash
echo "==================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ollama Setup & Performance Tuning"
echo "==================================================================="

sudo apt-get update -y

# Install Ollama if not already installed
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
fi

# Configure systemd override: single parallel slot prevents CPU contention & RAM swap on t3.large
sudo mkdir -p /etc/systemd/system/ollama.service.d
cat << 'EOF' | sudo tee /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_KEEP_ALIVE=24h"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_HOST=0.0.0.0:11434"
Restart=always
RestartSec=3
EOF

sudo systemctl daemon-reload
sudo systemctl enable ollama
sudo systemctl restart ollama

export HOME="${HOME:-/root}"

echo "Waiting for Ollama service to listen on port 11434..."
for i in {1..15}; do
    if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "Ollama daemon is online."
        break
    fi
    sleep 2
done

# Pull qwen2.5:0.5b model and pre-warm into memory with 24h keep_alive and 512 context window
ollama pull qwen2.5:0.5b
curl -s http://localhost:11434/api/generate -d '{
  "model": "qwen2.5:0.5b",
  "prompt": "System check: respond OK.",
  "stream": false,
  "keep_alive": "24h",
  "options": {"num_predict": 5, "num_ctx": 512}
}' >/dev/null

echo "Testing Ollama API ping..."
curl -s http://localhost:11434/api/tags | grep -q "models" && echo "Ollama server is active and pre-warmed." || echo "Ollama starting..."