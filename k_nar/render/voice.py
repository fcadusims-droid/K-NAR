"""FormantTTSBackend — voz sintética não-verbal por síntese de formantes.

Não é fala com palavras (sem espeak/XTTS neste ambiente). É uma vocalização
"alienígena": uma fonte glotal (trem de harmônicos em F0) modelada por
ressonadores de formante e um envelope silábico derivado do texto. Serve para
o que a Camada DSP precisa provar AGORA: ritmo, timing de interrupção, cortes
limpos, panning e reverb — tudo audível, sem depender de um motor de voz externo.

Implementa o Protocol `TTSBackend`: devolve `RenderedClip` com `samples` (mono
float32) e `duration_ms` MEDIDO das amostras. Determinístico e memoizado por id,
então timing (passagem 2) e render usam exatamente o mesmo áudio.
"""

from __future__ import annotations

import numpy as np

from k_nar.models import SpeechEvent
from k_nar.tts.base import RenderedClip

# "Vozes": F0 base (Hz) e trio de formantes (Hz) por personagem. Timbres distintos.
_VOICES = {
    "Alien A": dict(f0=104.0, formants=(560.0, 1080.0, 2500.0), color=0.9),
    "Alien B": dict(f0=158.0, formants=(720.0, 1450.0, 2900.0), color=1.15),
}
_DEFAULT_VOICE = dict(f0=130.0, formants=(650.0, 1250.0, 2700.0), color=1.0)


def _biquad_bandpass(x: np.ndarray, f0: float, sr: int, q: float) -> np.ndarray:
    """Ressonador de formante (biquad band-pass, forma direta I)."""
    w0 = 2.0 * np.pi * f0 / sr
    alpha = np.sin(w0) / (2.0 * q)
    cosw = np.cos(w0)
    b0, b1, b2 = alpha, 0.0, -alpha
    a0, a1, a2 = 1.0 + alpha, -2.0 * cosw, 1.0 - alpha
    b0, b1, b2 = b0 / a0, b1 / a0, b2 / a0
    a1, a2 = a1 / a0, a2 / a0
    y = np.zeros_like(x)
    x1 = x2 = y1 = y2 = 0.0
    for i in range(len(x)):
        xi = x[i]
        yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, xi
        y2, y1 = y1, yi
        y[i] = yi
    return y


def _syllable_count(text: str) -> int:
    """Estimativa grosseira de sílabas ~ grupos de vogais."""
    vowels = "aeiouáéíóúâêôãõà"
    n, prev = 0, False
    for ch in text.lower():
        is_v = ch in vowels
        if is_v and not prev:
            n += 1
        prev = is_v
    return max(1, n)


class FormantTTSBackend:
    def __init__(self, sr: int = 24000, base_wps: float = 2.6):
        self.sr = sr
        self.base_wps = base_wps
        self._cache: dict[str, RenderedClip] = {}

    # ------------------------------------------------------------------ #
    def synthesize(self, event: SpeechEvent) -> RenderedClip:
        if event.id in self._cache:
            return self._cache[event.id]

        voice = _VOICES.get(event.character, _DEFAULT_VOICE)
        rate = event.voice.rate if event.voice.rate > 0 else 1.0
        # tensão 0..1 (resolvida de número OU rótulo, como no TimingPolicy)
        tension = self._tension(event.voice.tension)

        words = max(1, len(event.text.split()))
        seconds = words / (self.base_wps * rate)
        n = max(int(self.sr * seconds), int(0.35 * self.sr))
        t = np.arange(n, dtype=np.float32) / self.sr

        # --- Fonte glotal: harmônicos de F0 com contorno prosódico ---
        f0 = voice["f0"] * (1.0 + 0.18 * tension)            # tensão sobe o tom
        declination = 1.0 - 0.12 * (t / t[-1])               # frase "cai" no fim
        vibrato = 1.0 + (0.006 + 0.02 * tension) * np.sin(2 * np.pi * 5.2 * t)
        f0_track = f0 * declination * vibrato
        phase = 2 * np.pi * np.cumsum(f0_track) / self.sr
        source = np.zeros(n, dtype=np.float32)
        for k in range(1, 9):                                 # 8 harmônicos ~ pulso glotal
            source += (1.0 / k) * np.sin(k * phase)
        # jitter/aspereza cresce com a tensão (voz "quebrando")
        rng = np.random.default_rng(abs(hash(event.id)) % (2**32))
        source += (0.05 + 0.20 * tension) * rng.standard_normal(n).astype(np.float32)

        # --- Formantes: soma de 3 ressonadores (timbre da "voz") ---
        shaped = np.zeros(n, dtype=np.float32)
        for i, fc in enumerate(voice["formants"]):
            q = 8.0 + 4.0 * i
            gain = voice["color"] ** (i + 1)
            shaped += gain * _biquad_bandpass(source, fc * voice["color"], self.sr, q)

        # --- Envelope silábico: abre/fecha a boca N vezes (ritmo de fala) ---
        env = self._syllable_envelope(n, _syllable_count(event.text), rate, tension)
        out = shaped * env

        peak = float(np.max(np.abs(out))) or 1.0
        out = (out / peak * 0.9).astype(np.float32)

        clip = RenderedClip(
            event_id=event.id,
            duration_ms=int(round(1000 * n / self.sr)),
            sample_rate=self.sr,
            samples=out,
        )
        self._cache[event.id] = clip
        return clip

    # ------------------------------------------------------------------ #
    @staticmethod
    def _tension(value) -> float:
        labels = {"baixa": 0.15, "media": 0.5, "alta": 0.8, "extrema": 1.0}
        if isinstance(value, (int, float)):
            return float(min(max(value, 0.0), 1.0))
        return labels.get(str(value).strip().lower(), 0.0)

    def _syllable_envelope(self, n: int, syllables: int, rate: float, tension: float) -> np.ndarray:
        """Um envelope com `syllables` bumps raised-cosine — cadência de fala."""
        t = np.linspace(0.0, np.pi * syllables, n, dtype=np.float32)
        bumps = np.abs(np.sin(t))                       # N lóbulos
        floor = 0.12                                    # nunca zera de todo (voz contínua)
        env = floor + (1.0 - floor) * (bumps ** (1.3 - 0.5 * tension))
        # ataque/relaxamento global da frase
        attack = int(0.02 * self.sr)
        if attack > 1:
            env[:attack] *= np.linspace(0, 1, attack, dtype=np.float32)
            env[-attack:] *= np.linspace(1, 0, attack, dtype=np.float32)
        return env
