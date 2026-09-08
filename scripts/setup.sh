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
  echo "[setup] XTTS-v2 — combo de deps VALIDADO (100% local, CPU)."
  # torch/torchaudio 2.8 CPU: alinhados e < 2.9 (evita a exigência de torchcodec/ffmpeg
  # que o torch >= 2.9 introduz). Índice CPU-only: wheel leve, sem CUDA.
  echo "[setup]  - torch + torchaudio (CPU)..."
  pip install --quiet "torch==2.8.0" "torchaudio==2.8.0" --index-url https://download.pytorch.org/whl/cpu
  # transformers < 5: o coqui 0.27 usa APIs removidas no transformers 5.x.
  echo "[setup]  - coqui-tts + transformers (4.x)..."
  pip install --quiet coqui-tts "transformers>=4.57,<5"
  echo "[setup]  ok. O modelo XTTS (~1.8GB) baixa no 1º uso."
fi

echo "[setup] ok. rode:  python -m unittest discover -s tests"
echo "        e:      python -m k_nar examples/roteiro_yt_exemplo.txt --motor formante"
