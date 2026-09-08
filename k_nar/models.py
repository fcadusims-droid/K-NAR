"""Modelo de dados do narrador — o mínimo que o motor de voz consome.

Cada frase do roteiro vira um `SpeechEvent`: um texto + parâmetros de voz. Para o
narrador, esses parâmetros são NEUTROS (o narrador não "atua"): a única alavanca de
performance é `rate` (velocidade da leitura). Os campos de emoção/tensão existem só
porque os backends de voz (XTTS/formante) compartilham este contrato — ficam em
"neutro"/0 na narração.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Rótulos qualitativos de tensão -> escalar 0..1. Fonte única lida pela ProsodyPolicy
# e pelo backend sintético. O narrador usa sempre 0 (neutro).
TENSION_LABELS = {"baixa": 0.15, "media": 0.5, "alta": 0.8, "extrema": 1.0}


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class VoiceParams:
    """Parâmetros RELATIVOS de voz. Nada aqui é absoluto: `rate` é multiplicador de
    velocidade, `pitch` é desvio de tom. No narrador ficam neutros (rate = velocidade)."""

    tension: Any = 0.0   # 0.0 calmo -> 1.0 pânico  (float ou rótulo); narrador = 0
    rate: float = 1.0    # multiplicador de velocidade (1.0 = neutro)
    pitch: float = 0.0   # desvio relativo de tom (-1.0 .. +1.0), 0 = neutro
    emotion: str = "neutro"
    intensity: float = 0.0


@dataclass
class SpeechEvent:
    """Um trecho de fala a sintetizar: identidade + texto + parâmetros de voz."""

    id: str
    character: str
    text: str
    voice: VoiceParams = field(default_factory=VoiceParams)
