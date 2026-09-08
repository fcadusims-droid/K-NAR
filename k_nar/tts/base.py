"""Contrato AGNÓSTICO de TTS — a fronteira que mantém o narrador desacoplado do motor.

O narrador não sabe (e não pode saber) se o áudio veio de um XTTS local, de uma API
paga ou de um stand-in sintético. Ele só depende deste `Protocol`. Trocar o motor de
voz = trocar a implementação, sem tocar na lógica de segmentação/montagem.

A peça crítica é `RenderedClip.duration_ms`: a duração REAL medida após a síntese — é
o que a montagem usa para posicionar as pausas com precisão.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from k_nar.models import SpeechEvent


@dataclass
class RenderedClip:
    """Resultado "seco" da síntese de UM trecho de fala."""

    event_id: str
    duration_ms: int          # duração REAL medida a partir das amostras
    audio: bytes | None = None  # buffer WAV opcional; None quando só há amostras
    sample_rate: int = 24000
    # Amostras de áudio mono (numpy float32 em [-1, 1]) quando o backend gera som.
    # Anotado como `object` de propósito: o contrato não importa numpy.
    samples: object | None = None


@runtime_checkable
class TTSBackend(Protocol):
    """Qualquer objeto com este método serve de backend — tipagem estrutural,
    sem herança obrigatória."""

    def synthesize(self, event: SpeechEvent) -> RenderedClip:
        ...
