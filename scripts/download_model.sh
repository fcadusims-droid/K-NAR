#!/usr/bin/env bash
# Baixa o LLM local do Director (Qwen2.5-1.5B-Instruct, GGUF Q4_K_M, ~1.1GB).
# Ungated (nao precisa de token). Roda em CPU via llama-cpp-python.
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL_DIR="models"
MODEL_FILE="qwen2.5-1.5b-instruct-q4_k_m.gguf"
URL="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/${MODEL_FILE}"

mkdir -p "$MODEL_DIR"
if [[ -f "${MODEL_DIR}/${MODEL_FILE}" ]]; then
  echo "[model] ja existe: ${MODEL_DIR}/${MODEL_FILE}"
  exit 0
fi

echo "[model] baixando ${MODEL_FILE} (~1.1GB)..."
curl -fL "$URL" -o "${MODEL_DIR}/${MODEL_FILE}"
echo "[model] ok: ${MODEL_DIR}/${MODEL_FILE}"
