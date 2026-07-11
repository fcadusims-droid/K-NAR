"""CachingTTS — cache de síntese em disco, endereçado por conteúdo.

Responde à primeira metade da pergunta de latência: como não deixar o TTS lento
(XTTS ~segundos/fala) travar o pipeline. A resposta é NÃO RE-SINTETIZAR. A chave
é um hash do que afeta o áudio (motor + voz + texto + prosódia relativa); se nada
disso mudou, o áudio volta do disco em milissegundos.

Efeito prático: iterar na linha de tempo, no DSP ou no reverb re-renderiza sem
re-sintetizar nenhuma fala. Só falas novas/alteradas pagam o custo neural.

Envolve qualquer `TTSBackend` (mock, formante, Piper, XTTS...).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from k_nar.models import SpeechEvent
from k_nar.tts.base import RenderedClip, TTSBackend


class CachingTTS:
    def __init__(self, inner: TTSBackend, cache_dir: str = ".knar_cache"):
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    # ------------------------------------------------------------------ #
    def _key(self, event: SpeechEvent) -> str:
        backend_id = getattr(self.inner, "backend_id", type(self.inner).__name__)
        payload = {
            "backend": backend_id,
            "texto": event.text,
            "personagem": event.character,
            "rate": round(float(event.voice.rate), 4),
            "pitch": round(float(event.voice.pitch), 4),
            "tensao": str(event.voice.tension),
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:24]

    def synthesize(self, event: SpeechEvent) -> RenderedClip:
        key = self._key(event)
        path = self.cache_dir / f"{key}.npz"
        if path.exists():
            self.hits += 1
            data = np.load(path, allow_pickle=False)
            return RenderedClip(
                event_id=event.id,
                duration_ms=int(data["duration_ms"]),
                sample_rate=int(data["sample_rate"]),
                samples=data["samples"],
            )

        self.misses += 1
        clip = self.inner.synthesize(event)
        if clip.samples is not None:
            np.savez(
                path,
                samples=np.asarray(clip.samples, dtype=np.float32),
                duration_ms=np.int64(clip.duration_ms),
                sample_rate=np.int64(clip.sample_rate),
            )
        # o event_id do cache é o do chamador (a mesma fala pode ter ids distintos)
        return RenderedClip(event.id, clip.duration_ms, sample_rate=clip.sample_rate,
                            samples=clip.samples)
