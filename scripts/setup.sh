#!/usr/bin/env bash
# Setup do K-NAR (narrador). Reinstala o que o ambiente efêmero perde entre sessões.
#
#   scripts/setup.sh            # numpy (montagem) — leve; roda o motor 'formante'
#   scripts/setup.sh --xtts     # + coqui-tts + torch (voz XTTS de alta qualidade)
#
# A segmentação do roteiro e a leitura do front-matter são stdlib puro. numpy só é
# exigida na montagem do áudio; o XTTS (torch/coqui) é a voz neural real (pesada).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[setup] numpy (montagem do áudio)..."
pip install --quiet numpy

if [[ "${1:-}" == "--xtts" ]]; then
  echo "[setup] XTTS-v2 (coqui-tts + torch) — pesado; o modelo (~1.8GB) baixa no 1º uso..."
  pip install --quiet coqui-tts torch
fi

echo "[setup] ok. rode:  python -m unittest discover -s tests"
echo "        e:      python -m k_nar examples/roteiro_yt_exemplo.txt --motor formante"
