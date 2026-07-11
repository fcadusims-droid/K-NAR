"""Subpacote de backends de TTS. O core só depende do Protocol em `base`."""

from k_nar.tts.base import RenderedClip, TTSBackend
from k_nar.tts.mock import MockTTSBackend

__all__ = ["RenderedClip", "TTSBackend", "MockTTSBackend"]
