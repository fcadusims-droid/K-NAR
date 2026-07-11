"""Primitivos de DSP — a física do áudio que a EDL sozinha não resolve.

Responde diretamente às três críticas ao modelo puramente matemático:

* `apply_fades`        -> mata o clique digital do corte frio (fade raised-cosine).
* `snap_to_valley`     -> desliza o corte até um vale de energia (silêncio entre
                          fonemas), stand-in leve de forced alignment: não decepa
                          no meio de uma plosiva.
* `equal_power_pan`    -> panning com lei de potência constante (palco estéreo).
* `fft_convolve`       -> reverberação CONVOLUTIVA real (Impulse Response).
"""

from __future__ import annotations

import numpy as np


def raised_cosine_window(n: int, rising: bool) -> np.ndarray:
    """Rampa suave 0->1 (ou 1->0) de `n` amostras. Sem descontinuidade de derivada
    nas pontas => sem clique."""
    if n <= 1:
        return np.ones(max(n, 0), dtype=np.float32)
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    w = 0.5 * (1.0 - np.cos(np.pi * t))  # 0 -> 1, suave
    return w if rising else w[::-1].copy()


def apply_fades(mono: np.ndarray, fade_in: int, fade_out: int) -> np.ndarray:
    """Aplica micro-fades nas bordas (in-place numa cópia). Anti-clique."""
    out = mono.astype(np.float32, copy=True)
    n = len(out)
    fi = int(min(max(fade_in, 0), n))
    fo = int(min(max(fade_out, 0), n))
    if fi > 1:
        out[:fi] *= raised_cosine_window(fi, rising=True)
    if fo > 1:
        out[n - fo:] *= raised_cosine_window(fo, rising=False)
    return out


def short_time_energy(mono: np.ndarray, win: int) -> np.ndarray:
    """Energia de curto prazo (RMS^2 suavizado). Usada p/ achar silêncios."""
    win = max(1, int(win))
    power = mono.astype(np.float32) ** 2
    kernel = np.ones(win, dtype=np.float32) / win
    return np.convolve(power, kernel, mode="same")


def snap_to_valley(mono: np.ndarray, target: int, window: int, floor: int,
                   smooth_win: int = 120) -> int:
    """Desliza `target` (amostra) até o ponto de MENOR energia dentro de +/- `window`.

    É o remédio pragmático contra "cortar no meio de uma consoante": em vez de
    cortar exatamente onde a matemática mandou, cortamos no vale de energia mais
    próximo (tipicamente o silêncio entre palavras). `floor` garante que nunca
    encurtamos além do mínimo audível decidido pela política. `smooth_win` é a
    janela de energia em amostras (~5 ms na taxa de amostragem da cena).
    """
    n = len(mono)
    if n == 0:
        return 0
    target = int(np.clip(target, 0, n))
    if window <= 0:
        return target
    lo = max(floor, target - window)
    hi = min(n, target + window)
    if hi <= lo:
        return target
    energy = short_time_energy(mono, win=smooth_win)
    idx = int(np.argmin(energy[lo:hi])) + lo
    return idx


def equal_power_pan(mono: np.ndarray, pan: int) -> np.ndarray:
    """Espalha um sinal mono em estéreo (2, N) com lei de potência constante.
    pan: -100 (esquerda) .. 0 (centro) .. +100 (direita)."""
    p = float(np.clip(pan, -100, 100))
    theta = (p + 100.0) / 200.0 * (np.pi / 2.0)  # 0 .. pi/2
    left = np.cos(theta)
    right = np.sin(theta)
    return np.stack([mono * left, mono * right]).astype(np.float32)


def fft_convolve(signal: np.ndarray, ir: np.ndarray) -> np.ndarray:
    """Convolução linear via FFT (rápida). Base da reverberação convolutiva."""
    n = len(signal) + len(ir) - 1
    size = 1 << (n - 1).bit_length()
    spec = np.fft.rfft(signal, size) * np.fft.rfft(ir, size)
    return np.fft.irfft(spec, size)[:n].astype(np.float32)


def convolution_reverb(stereo: np.ndarray, ir: np.ndarray, wet: float) -> np.ndarray:
    """Aplica o MESMO IR nos dois canais (bus único) e mistura dry+wet.

    Usar um IR só p/ a cena inteira é o que unifica as vozes no mesmo espaço
    físico (coesão acústica) — em vez de cada voz soar gravada num vácuo isolado.
    """
    wet = float(np.clip(wet, 0.0, 1.0))
    out = np.zeros_like(stereo)
    for ch in range(stereo.shape[0]):
        rev = fft_convolve(stereo[ch], ir)[: stereo.shape[1]]
        out[ch] = (1.0 - wet) * stereo[ch] + wet * rev
    return out.astype(np.float32)


def peak_normalize(stereo: np.ndarray, target: float = 0.89) -> np.ndarray:
    """Normaliza pelo pico (evita clipping). target ~ -1 dBFS."""
    peak = float(np.max(np.abs(stereo))) if stereo.size else 0.0
    if peak < 1e-9:
        return stereo
    return (stereo * (target / peak)).astype(np.float32)
