"""Backend de TTS FALSO — determinístico, sem dependências, sem gerar áudio.

Serve a um propósito preciso: provar e testar a lógica das duas passagens sem
precisar de um motor de voz instalado. Ele "mede" uma duração plausível a partir
da contagem de palavras e do multiplicador de velocidade, de forma reprodutível.

Assim a PASSAGEM 3 (alocação temporal) pode ser exercitada e testada de forma
100% offline. Trocar isto pelo XTTS real não muda uma linha do Orquestrador.
"""

from __future__ import annotations

from k_nar.models import SpeechEvent
from k_nar.tts.base import RenderedClip

# Ritmo de fala neutro de referência (palavras por segundo).
_BASE_WPS = 2.6
# Piso: nenhuma fala dura menos que isto (respiração, ataque da consoante etc.).
_FLOOR_MS = 350


class MockTTSBackend:
    """Estima duração ~ palavras / (wps * rate). Determinístico por construção."""

    def __init__(self, base_wps: float = _BASE_WPS, floor_ms: int = _FLOOR_MS):
        self.base_wps = base_wps
        self.floor_ms = floor_ms

    def synthesize(self, event: SpeechEvent) -> RenderedClip:
        words = max(1, len(event.text.split()))
        rate = event.voice.rate if event.voice.rate > 0 else 1.0
        seconds = words / (self.base_wps * rate)
        duration_ms = max(self.floor_ms, round(seconds * 1000))
        return RenderedClip(event_id=event.id, duration_ms=duration_ms, audio=None)
