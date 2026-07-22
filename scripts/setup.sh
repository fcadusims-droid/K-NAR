#!/usr/bin/env bash
# Setup do K-NAR. Reinstala tudo que o ambiente efemero perde entre sessoes.
#
#   scripts/setup.sh          # deps de DSP (numpy + pedalboard) — leve, rapido
#   scripts/setup.sh --llm    # + llama-cpp-python (compila) + baixa o modelo GGUF
#
# O core roda sem nada disso (stdlib). Estas deps sao so p/ render e Director-LLM.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[setup] deps de DSP (numpy + pedalboard)..."
pip install --quiet numpy pedalboard

echo "[setup] TTS neural (Piper, CPU) + forced alignment (onnx) + voz PT-BR..."
# onnx habilita o forced alignment do Piper (patch do grafo p/ expor durações de
# fonema); sem ele, o corte de interrupção cai no snap de energia (fallback).
pip install --quiet piper-tts onnx
bash scripts/download_piper.sh
bash scripts/download_piper.sh jeff   # 2a voz p/ multivoz (narrador/personagens)

if [[ "${1:-}" == "--llm" ]]; then
  echo "[setup] llama-cpp-python (compila; pode levar alguns minutos)..."
  CMAKE_ARGS="-DGGML_NATIVE=OFF" pip install --quiet llama-cpp-python
  bash scripts/download_model.sh
fi

echo "[setup] ok. rode:  python -m unittest discover -s tests"
