"""Prova numérica + audível dos dois refinamentos que preparam o terreno p/ o XTTS:

1. TRIM de silêncio: simula o padding que um motor neural injeta nas bordas e
   mostra que a duração MEDIDA volta a ser só a da fala (senão a proporção da
   interrupção e o snap_to_valley corrompem).

2. CROSSFADE equal-power: sobrepõe duas vozes altas e compara a SOMA LINEAR (que
   estoura o teto e distorce) com o crossfade equal-power (potência constante,
   sem clipping).

Gera dois WAVs para ouvir a diferença: build_audio/clip_linear.wav (distorcido)
vs build_audio/clip_equalpower.wav (limpo).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from k_nar.models import EntryDynamics, EntryType, ExitDynamics, SpeechEvent, VoiceParams
from k_nar.render.dsp import fade_window, trim_silence
from k_nar.render.renderer import TimelineRenderer
from k_nar.render.voice import FormantTTSBackend

SR = 24000
OUT = Path("build_audio")
OUT.mkdir(parents=True, exist_ok=True)


def _ev(eid, char, txt):
    return SpeechEvent(id=eid, character=char, text=txt, voice=VoiceParams(tension="alta"),
                       entry=EntryDynamics(type=EntryType.SEQUENTIAL),
                       exit=ExitDynamics())


def prova_trim() -> None:
    print("=" * 68)
    print("1) TRIM DE SILÊNCIO (padding de motor neural)")
    print("=" * 68)
    backend = FormantTTSBackend(sr=SR)
    clip = backend.synthesize(_ev("a", "Alien A", "o nucleo nao deve ser ativado"))
    fala = np.asarray(clip.samples, dtype=np.float32)

    pad_ini, pad_fim = int(0.150 * SR), int(0.200 * SR)  # 150ms / 200ms de silêncio
    padded = np.concatenate([np.zeros(pad_ini, np.float32), fala, np.zeros(pad_fim, np.float32)])

    trimmed, lead, trail = trim_silence(padded, threshold_db=-45.0, keep_ms=8.0, sr=SR)
    print(f"  fala pura            : {len(fala)/SR*1000:6.0f} ms")
    print(f"  + padding neural     : {len(padded)/SR*1000:6.0f} ms   (+350 ms de silêncio morto)")
    print(f"  após trim            : {len(trimmed)/SR*1000:6.0f} ms   (removidos {lead/SR*1000:.0f}ms ini / {trail/SR*1000:.0f}ms fim)")
    erro = abs(len(trimmed) - len(fala)) / SR * 1000
    print(f"  erro vs fala pura    : {erro:6.1f} ms   (só a folga de keep_ms) -> timeline confiável\n")


def prova_crossfade() -> None:
    print("=" * 68)
    print("2) CROSSFADE EQUAL-POWER vs SOMA LINEAR (zona de sobreposição)")
    print("=" * 68)
    backend = FormantTTSBackend(sr=SR)
    a = np.asarray(backend.synthesize(_ev("a", "Alien A", "voce nao vai me deter agora")).samples)
    b = np.asarray(backend.synthesize(_ev("b", "Alien B", "o inevitavel ja chegou aqui")).samples)
    n = min(len(a), len(b))
    a, b = a[:n] * 0.9, b[:n] * 0.9  # duas vozes ALTAS

    # soma linear crua (o que o "+" ingênuo faz)
    linear = a + b
    # crossfade equal-power: a afunda (cos), b sobe (sin) ao longo do trecho
    fin = fade_window(n, rising=True, curve="equal_power")
    fout = fade_window(n, rising=False, curve="equal_power")
    equalp = a * fout + b * fin

    print(f"  pico soma linear     : {np.abs(linear).max():.3f}   (> 1.0 => CLIPPING/distorção)")
    print(f"  pico equal-power     : {np.abs(equalp).max():.3f}   (<= 1.0 => limpo, 0 dB somado)")

    # grava os dois para ouvir (linear é hard-clipado p/ [-1,1] -> distorção audível)
    r = TimelineRenderer(sr=SR)
    r.write_wav(str(OUT / "clip_linear.wav"), np.stack([np.clip(linear, -1, 1)] * 2))
    r.write_wav(str(OUT / "clip_equalpower.wav"), np.stack([equalp, equalp]))
    print(f"\n  audio: {OUT/'clip_linear.wav'} (distorcido) vs {OUT/'clip_equalpower.wav'} (limpo)\n")


if __name__ == "__main__":
    prova_trim()
    prova_crossfade()
