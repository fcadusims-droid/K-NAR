#!/usr/bin/env bash
# Baixa uma voz neural PT-BR do Piper. Piper roda em CPU e e rapido (~0.05s/fala).
# Vozes PT-BR disponiveis: faber (default), jeff, cadu, edresson.
# Vozes de amostra: https://rhasspy.github.io/piper-samples
#
#   scripts/download_piper.sh          # faber-medium (default)
#   scripts/download_piper.sh jeff     # segunda voz (p/ voz por personagem)
set -euo pipefail
cd "$(dirname "$0")/.."

VOICE="${1:-faber}"
QUALITY="medium"
DIR="models/piper"
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/${VOICE}/${QUALITY}"
STEM="pt_BR-${VOICE}-${QUALITY}"
mkdir -p "$DIR"

for f in "${STEM}.onnx" "${STEM}.onnx.json"; do
  if [[ -f "${DIR}/${f}" ]]; then
    echo "[piper] ja existe: ${DIR}/${f}"
  else
    echo "[piper] baixando ${f}..."
    curl -fL "${BASE}/${f}" -o "${DIR}/${f}"
  fi
done
echo "[piper] ok: ${DIR}/${STEM}.onnx"
