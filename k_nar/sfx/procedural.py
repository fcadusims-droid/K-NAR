"""ProceduralSfxBackend — SÍNTESE determinística de efeitos, sem arquivos.

É o stand-in runnable da camada de som, como o `FormantTTSBackend` é para a voz:
não são samples reais, mas efeitos plausíveis (rajada de ruído com decaimento para
um tiro; ruído filtrado modulado para vento; splashes para passos na poça) — o
bastante para PROVAR o pipeline: pacing, mixagem, e principalmente o DUCKING, sem
depender de uma biblioteca de áudio licenciada. Trocar por `LibrarySfxBackend`
(samples reais) não muda uma linha do Orquestrador nem do renderer.

Cada tag mapeia para um gerador determinístico (semente derivada do tag), então o
mesmo som soa igual entre a medição de duração e o render.
"""

from __future__ import annotations

import zlib

import numpy as np

from k_nar.tts.base import RenderedClip


def _rng(tag: str) -> np.random.Generator:
    # crc32 é ESTÁVEL entre processos (hash() é salgado por PYTHONHASHSEED); sem isso
    # o mesmo tag soaria diferente a cada execução — quebrando a reprodutibilidade.
    return np.random.default_rng(zlib.crc32(tag.encode("utf-8")) & 0xFFFFFFFF)


def _noise(n: int, rng) -> np.ndarray:
    return rng.standard_normal(n).astype(np.float32)


def _lowpass(x: np.ndarray, coeff: float) -> np.ndarray:
    """Passa-baixa one-pole (escurece). coeff em [0,1): maior = mais escuro."""
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = coeff * acc + (1.0 - coeff) * x[i]
        y[i] = acc
    return y


def _highpass(x: np.ndarray, coeff: float) -> np.ndarray:
    return (x - _lowpass(x, coeff)).astype(np.float32)


def _exp_env(n: int, decay: float) -> np.ndarray:
    """Envelope de decaimento exponencial (ataque instantâneo)."""
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    return np.exp(-decay * t).astype(np.float32)


def _norm(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = float(np.max(np.abs(x))) or 1.0
    return (x / m * peak).astype(np.float32)


# --------------------------------------------------------------------------- #
#  Geradores por tag (mono float32). Cada um recebe (sr, dur_s, rng).         #
# --------------------------------------------------------------------------- #
def _gun(sr, dur, rng):
    n = int(sr * dur)
    burst = _noise(n, rng) * _exp_env(n, 22.0)
    thump = np.sin(2 * np.pi * 70 * np.arange(n) / sr) * _exp_env(n, 30.0)
    return _norm(burst + 0.6 * thump)


def _explosion(sr, dur, rng):
    n = int(sr * dur)
    body = _lowpass(_noise(n, rng), 0.6) * _exp_env(n, 6.0)
    rumble = np.sin(2 * np.pi * 45 * np.arange(n) / sr) * _exp_env(n, 4.0)
    return _norm(body + 0.8 * rumble)


def _impact(sr, dur, rng):
    n = int(sr * dur)
    return _norm(_lowpass(_noise(n, rng), 0.4) * _exp_env(n, 26.0))


def _glass(sr, dur, rng):
    n = int(sr * dur)
    shards = _highpass(_noise(n, rng), 0.2) * _exp_env(n, 10.0)
    ring = sum(np.sin(2 * np.pi * f * np.arange(n) / sr) * _exp_env(n, 14.0)
               for f in (2200, 3300, 5100))
    return _norm(shards + 0.3 * ring)


def _thunder(sr, dur, rng):
    n = int(sr * dur)
    env = np.minimum(np.linspace(0, 3, n), _exp_env(n, 3.0) * 3)
    return _norm(_lowpass(_noise(n, rng), 0.72) * env)


def _footsteps(sr, dur, rng, splash=False):
    n = int(sr * dur)
    out = np.zeros(n, dtype=np.float32)
    steps = max(2, int(dur / 0.45))
    for k in range(steps):
        start = max(0, int((k + rng.uniform(-0.05, 0.05)) * sr * 0.45))  # nunca negativo
        if start >= n:
            break
        ln = int(sr * (0.14 if splash else 0.06))
        seg = _noise(ln, rng)
        seg = _highpass(seg, 0.25) if splash else _lowpass(seg, 0.5)
        seg = seg * _exp_env(ln, 8.0 if splash else 20.0)
        end = min(n, start + ln)
        out[start:end] += seg[: end - start]
    return _norm(out)


def _door_creak(sr, dur, rng):
    n = int(sr * dur)
    t = np.arange(n) / sr
    # tom rangente com pitch subindo e vibrato áspero
    f = 180 + 120 * (t / dur)
    creak = np.sin(2 * np.pi * f * t) * (1 + 0.5 * np.sin(2 * np.pi * 11 * t))
    env = np.sin(np.pi * t / dur) ** 0.5
    return _norm(creak.astype(np.float32) * env + 0.1 * _noise(n, rng) * env)


def _wind(sr, dur, rng):
    n = int(sr * dur)
    base = _lowpass(_noise(n, rng), 0.9)
    gust = 0.5 + 0.5 * np.sin(2 * np.pi * 0.2 * np.arange(n) / sr)
    return _norm(base * gust.astype(np.float32))


def _rain(sr, dur, rng):
    n = int(sr * dur)
    return _norm(_highpass(_noise(n, rng), 0.5) * 0.8)


def _engine(sr, dur, rng):
    n = int(sr * dur)
    t = np.arange(n) / sr
    buzz = sum(np.sin(2 * np.pi * f * t) for f in (60, 120, 180)).astype(np.float32)
    return _norm(buzz + 0.3 * _lowpass(_noise(n, rng), 0.7))


def _siren(sr, dur, rng):
    n = int(sr * dur)
    t = np.arange(n) / sr
    f = 650 + 250 * np.sin(2 * np.pi * 0.5 * t)
    return _norm(np.sin(2 * np.pi * f * t).astype(np.float32))


def _forest_night(sr, dur, rng):
    n = int(sr * dur)
    bed = _lowpass(_noise(n, rng), 0.85) * 0.4
    # grilos: tom agudo pulsante; um pássaro esporádico
    t = np.arange(n) / sr
    crickets = 0.15 * (np.sin(2 * np.pi * 4200 * t) *
                       (0.5 + 0.5 * np.sin(2 * np.pi * 18 * t))).astype(np.float32)
    return _norm(bed + crickets)


def _crowd(sr, dur, rng):
    n = int(sr * dur)
    return _norm(_lowpass(_noise(n, rng), 0.8) *
                 (0.6 + 0.4 * np.sin(2 * np.pi * 0.7 * np.arange(n) / sr)).astype(np.float32))


# tag -> (gerador, duração padrão em s)
_SFX = {
    "tiro": (_gun, 0.5), "explosao": (_explosion, 1.4), "batida": (_impact, 0.4),
    "vidro_quebra": (_glass, 0.7), "trovao": (_thunder, 2.2),
    "passos": (lambda sr, d, r: _footsteps(sr, d, r, False), 1.6),
    "passos_poca": (lambda sr, d, r: _footsteps(sr, d, r, True), 1.6),
    "porta_range": (_door_creak, 1.3), "sirene": (_siren, 2.0), "alarme": (_siren, 2.0),
}
_AMBIENCE = {
    "floresta_noite": (_forest_night, 4.0), "chuva": (_rain, 4.0),
    "vento": (_wind, 4.0), "motor": (_engine, 4.0), "multidao": (_crowd, 4.0),
    "cidade": (_crowd, 4.0),
}


class ProceduralSfxBackend:
    """Sintetiza SFX/ambiência por tag. Determinístico. Satisfaz `SfxBackend`."""

    def __init__(self, sr: int = 22050):
        self.sr = sr

    @property
    def backend_id(self) -> str:
        return f"procedural_sfx:{self.sr}"

    def render(self, event) -> RenderedClip:
        tag = getattr(event, "tag", "") or ""
        gen_dur = _SFX.get(tag) or _AMBIENCE.get(tag)
        if gen_dur is None:
            # tag desconhecido: um blip curto e neutro (auditável, nunca silêncio mudo)
            gen_dur = ((lambda sr, d, r: _norm(_noise(int(sr * d), r) * _exp_env(int(sr * d), 12.0))), 0.25)
        gen, dur = gen_dur
        audio = gen(self.sr, dur, _rng(tag))
        return RenderedClip(
            event_id=event.id,
            duration_ms=int(round(1000 * len(audio) / self.sr)),
            sample_rate=self.sr,
            samples=audio,
        )
