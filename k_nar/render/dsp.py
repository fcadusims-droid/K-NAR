"""Primitivos de áudio usados pelo narrador (numpy).

Só o que o pipeline de narração precisa:

* `trim_silence`     -> remove o padding de silêncio que os motores neurais injetam
                        nas bordas de cada frase, ANTES de medir a duração.
* `resample_linear`  -> reamostragem por interpolação linear; base do pitch shift do
                        XTTS (gera a fala mais lenta e reamostra de volta ao alvo).
"""

from __future__ import annotations

import numpy as np


def trim_silence(mono: np.ndarray, threshold_db: float = -45.0,
                 keep_ms: float = 8.0, sr: int = 24000) -> tuple[np.ndarray, int, int]:
    """Remove silêncio (padding) do INÍCIO e FIM do áudio retornado pelo TTS.

    Motores neurais (XTTS, ...) injetam silêncio residual variável nas bordas. Se esse
    tempo morto entrar na montagem, ele soma às pausas do roteiro e desregula o ritmo.
    Este trim garante que a duração MEDIDA seja estritamente a da fala.

    Mantém `keep_ms` de folga em cada lado (evita cortar o ataque/decay da fala).
    Devolve (áudio_trimado, amostras_removidas_inicio, amostras_removidas_fim).
    """
    n = len(mono)
    if n == 0:
        return mono, 0, 0
    thresh = 10.0 ** (threshold_db / 20.0)
    env = np.abs(mono.astype(np.float32))
    above = np.where(env > thresh)[0]
    if len(above) == 0:
        return mono[:0], 0, n  # tudo silêncio
    keep = int(keep_ms * sr / 1000.0)
    start = max(0, int(above[0]) - keep)
    end = min(n, int(above[-1]) + 1 + keep)
    return mono[start:end].astype(np.float32), start, n - end


def resample_linear(mono: np.ndarray, ratio: float) -> np.ndarray:
    """Reamostra por interpolação linear para `ratio` = tamanho_saida/tamanho_entrada.

    Base do pitch shift SEM phase vocoder: o motor gera a fala mais lenta (via
    length_scale) e reamostrar de volta ao tamanho-alvo sobe o pitch mantendo a
    duração — aproveitando o time-stretch neural de alta qualidade do próprio motor.
    """
    n = len(mono)
    if n == 0:
        return mono
    m = max(1, int(round(n * ratio)))
    x_old = np.linspace(0.0, 1.0, n, dtype=np.float64)
    x_new = np.linspace(0.0, 1.0, m, dtype=np.float64)
    return np.interp(x_new, x_old, mono).astype(np.float32)
