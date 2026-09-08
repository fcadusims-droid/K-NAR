"""Subpacote de backends de TTS. O narrador só depende do Protocol em `base`."""

from k_nar.tts.base import RenderedClip, TTSBackend

__all__ = ["RenderedClip", "TTSBackend"]
