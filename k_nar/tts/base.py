"""Contrato AGNÓSTICO de TTS (a fronteira que mantém o Orquestrador desacoplado).

O Orquestrador não sabe (e não pode saber) se o áudio veio de um XTTS local, de
uma API paga ou de um mock determinístico. Ele só depende deste `Protocol`. Trocar
o motor de voz = trocar a implementação, sem tocar em uma linha da lógica de ritmo.

A peça crítica que este contrato entrega é `RenderedClip.duration_ms`: a duração
REAL medida após a síntese. É esse número que a PASSAGEM 3 cruza com os metadados
relativos do LLM para alocar a linha de tempo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from k_nar.align import Alignment
from k_nar.models import SpeechEvent


@dataclass
class RenderedClip:
    """Resultado "seco" (sem reverb/DSP) da síntese de UM evento de fala."""

    event_id: str
    duration_ms: int          # duração REAL medida — quebra a dependência circular
    audio: bytes | None = None  # buffer WAV opcional; None no modo mock (só mede tempo)
    sample_rate: int = 24000
    # Amostras de áudio mono (numpy float32 em [-1, 1]) quando o backend gera som.
    # Anotado como `object` de propósito: o CORE não importa numpy; só a camada
    # de render (que já depende de numpy) preenche/lê este campo.
    samples: object | None = None
    # Forced alignment (fonema→amostra) quando o backend o exporta (ex.: Piper com
    # include_alignments). É DADO PURO (stdlib): permite o Orquestrador resolver o
    # corte de interrupção numa fronteira de fonema REAL, sem tocar no áudio. None
    # nos backends que não alinham (mock/formante) — aí o renderer cai no snap de energia.
    alignment: "Alignment | None" = None


@runtime_checkable
class TTSBackend(Protocol):
    """Qualquer objeto com este método serve de backend — tipagem estrutural,
    sem herança obrigatória."""

    def synthesize(self, event: SpeechEvent) -> RenderedClip:
        ...
