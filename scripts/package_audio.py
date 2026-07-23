#!/usr/bin/env python3
"""Empacota o áudio para ENTREGA sob um limite de tamanho, SEM perder qualidade.

O problema: um audiobook longo em qualidade máxima passa de 30 MB, e zip/rar quase não
comprime áudio (MP3/Opus já são comprimidos). A solução certa:

  1. Codec eficiente: OPUS rende a qualidade do MP3 128k com ~metade do tamanho —
     um audiobook inteiro costuma caber em UM arquivo < 30 MB, com ótima voz.
  2. Se ainda passar do limite, DIVIDIR em partes (cortando num silêncio, não no meio
     de uma palavra), cada parte < limite.

Uso:
    python scripts/package_audio.py entrada.wav                 # -> .ogg (Opus) < 28 MB
    python scripts/package_audio.py entrada.wav --formato mp3   # partes .mp3
    python scripts/package_audio.py entrada.wav --max-mb 25 --bitrate 96

Requer numpy. Opus via `soundfile` (libsndfile); MP3 via `lameenc` (fallback).
"""

from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np


def _read_wav(path: str):
    with wave.open(path, "rb") as w:
        n, ch, sr = w.getnframes(), w.getnchannels(), w.getframerate()
        pcm = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float32) / 32768.0
    audio = pcm.reshape(-1, ch) if ch > 1 else pcm.reshape(-1, 1)
    return audio, sr


def _mp3_bytes(audio: np.ndarray, sr: int, bitrate: int) -> bytes:
    import lameenc
    ch = audio.shape[1]
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    enc = lameenc.Encoder()
    enc.set_bit_rate(bitrate); enc.set_in_sample_rate(sr)
    enc.set_channels(ch); enc.set_quality(2)
    return enc.encode(pcm) + enc.flush()


def _write_opus(audio: np.ndarray, sr: int, path: str, bitrate: int) -> None:
    import soundfile as sf
    # Opus só aceita 8/12/16/24/48 kHz — reamostra p/ 48k se preciso (linear, barato).
    if sr not in (8000, 12000, 16000, 24000, 48000):
        ratio = 48000 / sr
        n = int(round(audio.shape[0] * ratio))
        x_old = np.linspace(0, 1, audio.shape[0]); x_new = np.linspace(0, 1, n)
        audio = np.stack([np.interp(x_new, x_old, audio[:, c])
                          for c in range(audio.shape[1])], axis=1).astype(np.float32)
        sr = 48000
    sf.write(path, audio, sr, format="OGG", subtype="OPUS")


def _silence_cuts(mono: np.ndarray, sr: int, n_parts: int, search_s: float = 6.0):
    """Pontos de corte perto das divisões iguais, deslizados p/ o vale de energia mais
    próximo (não corta no meio de uma fala). Devolve índices de amostra."""
    total = len(mono)
    cuts = []
    win = int(0.05 * sr)
    env = np.convolve(np.abs(mono), np.ones(win) / win, mode="same")
    for i in range(1, n_parts):
        target = int(total * i / n_parts)
        lo, hi = max(0, target - int(search_s * sr)), min(total, target + int(search_s * sr))
        cut = lo + int(np.argmin(env[lo:hi])) if hi > lo else target
        cuts.append(cut)
    return cuts


def package(audio: np.ndarray, sr: int, out_prefix: str, max_mb: float = 28.0,
            fmt: str = "opus", bitrate: int = 96) -> list[str]:
    """Escreve o áudio em 1+ arquivos, cada um <= max_mb. Devolve os caminhos."""
    max_bytes = int(max_mb * 1024 * 1024)
    ext = "ogg" if fmt == "opus" else "mp3"

    def _encode(seg: np.ndarray, path: str):
        if fmt == "opus":
            _write_opus(seg, sr, path, bitrate)
        else:
            Path(path).write_bytes(_mp3_bytes(seg, sr, bitrate))

    whole = f"{out_prefix}.{ext}"
    _encode(audio, whole)
    if Path(whole).stat().st_size <= max_bytes:
        return [whole]

    # passou do limite: divide em partes iguais (cortando em silêncio) até caber.
    Path(whole).unlink(missing_ok=True)
    size = _size_estimate(audio, sr, fmt, bitrate)
    n_parts = int(np.ceil(size / max_bytes))
    mono = audio.mean(axis=1)
    while True:
        cuts = [0] + _silence_cuts(mono, sr, n_parts) + [len(audio)]
        paths, ok = [], True
        for i in range(n_parts):
            seg = audio[cuts[i]:cuts[i + 1]]
            path = f"{out_prefix}.parte{i+1:02d}.{ext}"
            _encode(seg, path)
            paths.append(path)
            if Path(path).stat().st_size > max_bytes:
                ok = False
        if ok:
            return paths
        for p in paths:
            Path(p).unlink(missing_ok=True)
        n_parts += 1


def _size_estimate(audio, sr, fmt, bitrate) -> int:
    dur = audio.shape[0] / sr
    return int(bitrate * 1000 / 8 * dur)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav", help="arquivo .wav de entrada")
    ap.add_argument("-o", "--out", help="prefixo de saída (default: <wav sem extensão>)")
    ap.add_argument("--formato", "--format", dest="fmt", default="opus",
                    choices=["opus", "mp3"], help="opus (menor/melhor) | mp3 (universal)")
    ap.add_argument("--max-mb", type=float, default=28.0)
    ap.add_argument("--bitrate", type=int, default=96, help="kbps (opus 64-96 já é ótimo p/ voz)")
    args = ap.parse_args()

    audio, sr = _read_wav(args.wav)
    prefix = args.out or str(Path(args.wav).with_suffix(""))
    paths = package(audio, sr, prefix, max_mb=args.max_mb, fmt=args.fmt, bitrate=args.bitrate)
    for p in paths:
        mb = Path(p).stat().st_size / 1024 / 1024
        print(f"  {p}  ({mb:.1f} MB)")
    print(f"{len(paths)} arquivo(s), cada um <= {args.max_mb} MB")


if __name__ == "__main__":
    raise SystemExit(main())
