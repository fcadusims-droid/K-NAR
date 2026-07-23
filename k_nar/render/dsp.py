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


def fade_window(n: int, rising: bool, curve: str = "cosine") -> np.ndarray:
    """Rampa 0->1 (ou 1->0) de `n` amostras.

    curve="cosine": raised-cosine (Hann) — anti-clique nas bordas.
    curve="equal_power": sin/cos — para CROSSFADE entre fontes descorrelacionadas
    (vozes diferentes): garante g_out^2 + g_in^2 = 1 => potência acústica somada
    constante, sem estouro nem cancelamento na sobreposição.
    """
    if n <= 1:
        return np.ones(max(n, 0), dtype=np.float32)
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    if curve == "equal_power":
        w = np.sin(t * (np.pi / 2.0))          # 0->1, sin (potência constante)
    else:
        w = 0.5 * (1.0 - np.cos(np.pi * t))    # 0->1, raised-cosine
    return w.astype(np.float32) if rising else w[::-1].copy()


# retrocompat: nome antigo
def raised_cosine_window(n: int, rising: bool) -> np.ndarray:
    return fade_window(n, rising, "cosine")


def apply_fades(mono: np.ndarray, fade_in: int, fade_out: int,
                curve_in: str = "cosine", curve_out: str = "cosine") -> np.ndarray:
    """Aplica fades nas bordas (in-place numa cópia). `curve_*` escolhe a lei da
    rampa: 'cosine' (anti-clique) ou 'equal_power' (crossfade)."""
    out = mono.astype(np.float32, copy=True)
    n = len(out)
    fi = int(min(max(fade_in, 0), n))
    fo = int(min(max(fade_out, 0), n))
    if fi > 1:
        out[:fi] *= fade_window(fi, rising=True, curve=curve_in)
    if fo > 1:
        out[n - fo:] *= fade_window(fo, rising=False, curve=curve_out)
    return out


def trim_silence(mono: np.ndarray, threshold_db: float = -45.0,
                 keep_ms: float = 8.0, sr: int = 24000) -> tuple[np.ndarray, int, int]:
    """Remove silêncio (padding) do INÍCIO e FIM do áudio retornado pelo TTS.

    Motores neurais (XTTS, VALL-E, ...) injetam silêncio residual variável nas
    bordas. Se esse tempo morto entrar na linha de tempo, ele (a) corrompe o
    cálculo proporcional da interrupção e (b) faz o `snap_to_valley` travar no
    silêncio artificial em vez do vale entre fonemas. Este trim garante que a
    duração MEDIDA seja estritamente a da fala.

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


def resample_linear(mono: np.ndarray, ratio: float) -> np.ndarray:
    """Reamostra por interpolação linear para `ratio` = tamanho_saida/tamanho_entrada.

    Base do pitch shift SEM phase vocoder: o Piper gera a fala mais lenta (via
    length_scale), e reamostrar de volta ao tamanho-alvo sobe o pitch mantendo a
    duração — aproveitando o time-stretch neural de alta qualidade do próprio motor.
    """
    n = len(mono)
    if n == 0:
        return mono
    m = max(1, int(round(n * ratio)))
    x_old = np.linspace(0.0, 1.0, n, dtype=np.float64)
    x_new = np.linspace(0.0, 1.0, m, dtype=np.float64)
    return np.interp(x_new, x_old, mono).astype(np.float32)


def lowpass_1pole(mono: np.ndarray, cutoff_hz: float, sr: int) -> np.ndarray:
    """Passa-baixa one-pole (escurece o som). Base do 'abafamento' da distância: o ar
    absorve os agudos, então um som ao longe perde brilho. `cutoff_hz`<=0 -> sem efeito."""
    if cutoff_hz <= 0 or len(mono) == 0:
        return mono.astype(np.float32, copy=False)
    coeff = float(np.exp(-2.0 * np.pi * cutoff_hz / sr))  # 0..1, maior = mais escuro
    out = np.empty_like(mono, dtype=np.float32)
    acc = 0.0
    one_minus = 1.0 - coeff
    for i in range(len(mono)):
        acc = coeff * acc + one_minus * float(mono[i])
        out[i] = acc
    # NÃO renormaliza: a perda de nível dos agudos É o abafamento da distância. As
    # frequências baixas passam ~intactas, então a presença do "corpo" do som fica.
    return out


def peak_normalize(stereo: np.ndarray, target: float = 0.89) -> np.ndarray:
    """Normaliza pelo pico (evita clipping). target ~ -1 dBFS."""
    peak = float(np.max(np.abs(stereo))) if stereo.size else 0.0
    if peak < 1e-9:
        return stereo
    return (stereo * (target / peak)).astype(np.float32)


def rms_normalize(mono: np.ndarray, target_rms: float = 0.12,
                  max_peak: float = 0.95) -> np.ndarray:
    """Normaliza pela ENERGIA (RMS) — a loudness PERCEBIDA, não o pico.

    Sons densos (grilos, motor) têm RMS alto mesmo com pico baixo; normalizar por
    pico os deixa altos demais. Ambiências devem sentar num nível perceptual
    consistente, então normalizamos por RMS (com trava de pico anti-clip)."""
    x = np.asarray(mono, dtype=np.float32)
    r = float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0
    if r < 1e-9:
        return x
    scaled = x * (target_rms / r)
    peak = float(np.max(np.abs(scaled))) or 1.0
    if peak > max_peak:
        scaled *= max_peak / peak
    return scaled.astype(np.float32)


def clipping_stats(stereo: np.ndarray, ceiling: float = 0.999) -> dict:
    """Mede pico e clipping da mixagem (alimenta `qa.check_mix`).

    Devolve dado puro (dict de números) para o QA — que é stdlib — decidir o veredito
    sem depender de numpy.
    """
    a = np.abs(np.asarray(stereo, dtype=np.float32))
    size = int(a.size)
    peak = float(a.max()) if size else 0.0
    clipped = int((a >= ceiling).sum()) if size else 0
    return {"peak": peak, "clipped_samples": clipped,
            "clipped_ratio": (clipped / size) if size else 0.0}
