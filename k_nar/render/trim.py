"""TrimmedTTS — decorator de TTSBackend que remove o padding de silêncio.

Envolve QUALQUER backend (mock, formante, XTTS, API...) e devolve um `RenderedClip`
com o áudio já trimado e a `duration_ms` REMEDIDA — estritamente a fala. Assim o
Orquestrador nunca vê o tempo morto que motores neurais injetam nas bordas, e o
cálculo proporcional da interrupção + o `snap_to_valley` operam só sobre fonemas.

    backend = TrimmedTTS(XttsBackend(...), threshold_db=-45)
    Orquestrador(backend).render_scene(cena)   # timing correto, sem padding
"""

from __future__ import annotations

import numpy as np

from k_nar.models import SpeechEvent
from k_nar.render.dsp import trim_silence
from k_nar.tts.base import RenderedClip, TTSBackend


class TrimmedTTS:
    def __init__(self, inner: TTSBackend, threshold_db: float = -45.0,
                 keep_ms: float = 8.0):
        self.inner = inner
        self.threshold_db = threshold_db
        self.keep_ms = keep_ms
        self._cache: dict[str, RenderedClip] = {}

    @property
    def backend_id(self) -> str:
        # propaga a identidade do backend interno para a chave de cache
        inner_id = getattr(self.inner, "backend_id", type(self.inner).__name__)
        return f"trim({self.threshold_db}):{inner_id}"

    def synthesize(self, event: SpeechEvent) -> RenderedClip:
        if event.id in self._cache:
            return self._cache[event.id]

        clip = self.inner.synthesize(event)
        if clip.samples is None:
            # backend sem áudio (ex.: mock só-duração): nada a trimar.
            self._cache[event.id] = clip
            return clip

        sr = clip.sample_rate
        mono = np.asarray(clip.samples, dtype=np.float32)
        trimmed, lead, trail = trim_silence(mono, self.threshold_db, self.keep_ms, sr)
        if len(trimmed) == 0:
            trimmed = mono  # fala inteira abaixo do threshold: não descarta
            lead = 0

        # O forced alignment sofre o MESMO corte de bordas que o áudio: sem isso, as
        # fronteiras de fonema apontariam para índices do sinal pré-trim.
        alignment = clip.alignment
        if alignment is not None:
            alignment = alignment.trimmed(lead, len(trimmed))

        out = RenderedClip(
            event_id=clip.event_id,
            duration_ms=int(round(1000 * len(trimmed) / sr)),  # duração REMEDIDA
            sample_rate=sr,
            samples=trimmed,
            alignment=alignment,
        )
        self._cache[event.id] = out
        return out
