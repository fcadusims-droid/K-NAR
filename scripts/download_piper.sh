#!/usr/bin/env bash
# Baixa uma voz neural PT-BR do Piper (faber-medium, 22050 Hz, ~63MB).
# Piper roda em CPU e e rapido (~0.05s/fala). Vozes: https://rhasspy.github.io/piper-samples
set -euo pipefail
cd "$(dirname "$0")/.."

DIR="models/piper"
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium"
mkdir -p "$DIR"

for f in pt_BR-faber-medium.onnx pt_BR-faber-medium.onnx.json; do
  if [[ -f "${DIR}/${f}" ]]; then
    echo "[piper] ja existe: ${DIR}/${f}"
  else
    echo "[piper] baixando ${f}..."
    curl -fL "${BASE}/${f}" -o "${DIR}/${f}"
  fi
done
echo "[piper] ok: ${DIR}/pt_BR-faber-medium.onnx"
