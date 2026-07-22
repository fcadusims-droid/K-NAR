#!/usr/bin/env bash
# Baixa as vozes Piper de um IDIOMA (personagens + narrador).
#
#   scripts/download_lang.sh pt    # pt_BR: faber + jeff  (default)
#   scripts/download_lang.sh en    # en_US: amy + ryan
#   scripts/download_lang.sh es    # es_ES: davefx + sharvard
#
# Vozes por idioma: https://rhasspy.github.io/piper-samples
set -euo pipefail
cd "$(dirname "$0")/.."

LANG_CODE="${1:-pt}"
DIR="models/piper"
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main"
mkdir -p "$DIR"

# idioma -> "subpasta/voz/qualidade" para cada voz
case "$LANG_CODE" in
  pt|pt_BR|portugues) VOICES=("pt/pt_BR/faber/medium" "pt/pt_BR/jeff/medium") ;;
  en|en_US|english)   VOICES=("en/en_US/amy/medium" "en/en_US/ryan/medium") ;;
  es|es_ES|espanol)   VOICES=("es/es_ES/davefx/medium" "es/es_ES/sharvard/medium") ;;
  *) echo "idioma desconhecido: $LANG_CODE (use pt | en | es)"; exit 1 ;;
esac

for v in "${VOICES[@]}"; do
  lang_region="$(echo "$v" | cut -d/ -f2)"    # ex.: pt_BR
  voice="$(echo "$v" | cut -d/ -f3)"          # ex.: faber
  quality="$(echo "$v" | cut -d/ -f4)"        # ex.: medium
  stem="${lang_region}-${voice}-${quality}"
  for ext in onnx onnx.json; do
    f="${stem}.${ext}"
    if [[ -f "${DIR}/${f}" ]]; then
      echo "[piper] ja existe: ${DIR}/${f}"
    else
      echo "[piper] baixando ${f}..."
      curl -fL "${BASE}/${v}/${f}" -o "${DIR}/${f}"
    fi
  done
done
echo "[piper] ok: vozes de '${LANG_CODE}' em ${DIR}/"
