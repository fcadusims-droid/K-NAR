"""K-NAR — Motor de Performance Dramática (áudio drama autônomo).

Fluxo de duas passagens, orientado a linha de tempo:
    LLM (intenção relativa) -> TTS (duração real) -> Orquestrador (Timeline/EDL).

O core é stdlib puro: nenhuma dependência de áudio para calcular o ritmo.
"""

from k_nar.align import Alignment, PhonemeSpan
from k_nar.models import (
    DramaticPause,
    EntryDynamics,
    EntryType,
    ExitDynamics,
    Scene,
    SpeechEvent,
    VoiceParams,
)
from k_nar.orchestrator import Orquestrador
from k_nar.prosody import Prosody, ProsodyPolicy
from k_nar.qa import QAIssue, check_mix, check_timeline, format_report
from k_nar.schema import SchemaError, validate_scene
from k_nar.timeline import Placement, Timeline, TimingPolicy
from k_nar.tts.base import RenderedClip, TTSBackend
from k_nar.tts.mock import MockTTSBackend

__all__ = [
    "Alignment",
    "DramaticPause",
    "EntryDynamics",
    "EntryType",
    "ExitDynamics",
    "MockTTSBackend",
    "Orquestrador",
    "Placement",
    "PhonemeSpan",
    "Prosody",
    "ProsodyPolicy",
    "QAIssue",
    "RenderedClip",
    "Scene",
    "SchemaError",
    "SpeechEvent",
    "TTSBackend",
    "Timeline",
    "TimingPolicy",
    "VoiceParams",
    "check_mix",
    "check_timeline",
    "format_report",
    "validate_scene",
]

__version__ = "0.1.0"
