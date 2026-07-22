"""Testes do roteamento de voz por personagem — sem carregar modelos Piper.

Injeta um backend Piper FALSO via monkeypatch do import tardio, para exercitar o
roteamento (modelo/locutor por personagem, ritmo base, cache de backend) sem numpy.
"""

import unittest
from unittest import mock

from k_nar.models import SpeechEvent, VoiceParams
from k_nar.tts.base import RenderedClip
from k_nar.tts.multivoice import MultiVoiceTTSBackend, VoiceProfile


class _FakePiper:
    """Registra (modelo, speaker_id) e devolve um clip anotando o que recebeu."""

    instances = []

    def __init__(self, model_path, prosody=None, align=True, speaker_id=None):
        self.model_path = model_path
        self.speaker_id = speaker_id
        self.calls = []
        _FakePiper.instances.append(self)

    def synthesize(self, event):
        self.calls.append(event)
        return RenderedClip(event.id, duration_ms=1000, sample_rate=22050,
                            samples=[0.0])


def _patch_piper():
    # o import é tardio dentro de _backend: k_nar.tts.neural.PiperTTSBackend
    return mock.patch("k_nar.tts.neural.PiperTTSBackend", _FakePiper)


class TestMultiVoiceRouting(unittest.TestCase):
    def setUp(self):
        _FakePiper.instances = []

    def test_routes_to_per_character_model(self):
        profiles = {
            "Narrador": VoiceProfile(model_path="narr.onnx"),
            "Heroi": VoiceProfile(model_path="hero.onnx"),
        }
        mv = MultiVoiceTTSBackend("default.onnx", profiles)
        with _patch_piper():
            mv.synthesize(SpeechEvent("1", "Narrador", "era uma vez"))
            mv.synthesize(SpeechEvent("2", "Heroi", "eu vou!"))
            mv.synthesize(SpeechEvent("3", "Coadjuvante", "e eu?"))  # sem perfil -> default

        models = sorted(i.model_path for i in _FakePiper.instances)
        self.assertEqual(models, ["default.onnx", "hero.onnx", "narr.onnx"])

    def test_backend_is_cached_per_voice(self):
        profiles = {"A": VoiceProfile(model_path="m.onnx"),
                    "B": VoiceProfile(model_path="m.onnx")}  # MESMO modelo
        mv = MultiVoiceTTSBackend("default.onnx", profiles)
        with _patch_piper():
            mv.synthesize(SpeechEvent("1", "A", "oi"))
            mv.synthesize(SpeechEvent("2", "B", "ola"))
            mv.synthesize(SpeechEvent("3", "A", "de novo"))
        # A e B compartilham "m.onnx" -> um único backend carregado
        loaded = [i for i in _FakePiper.instances if i.model_path == "m.onnx"]
        self.assertEqual(len(loaded), 1)

    def test_speaker_id_forwarded(self):
        profiles = {"A": VoiceProfile(speaker_id=3)}
        mv = MultiVoiceTTSBackend("multi.onnx", profiles)
        with _patch_piper():
            mv.synthesize(SpeechEvent("1", "A", "oi"))
        be = _FakePiper.instances[0]
        self.assertEqual(be.speaker_id, 3)

    def test_character_rate_multiplies_relative_rate(self):
        profiles = {"Devagar": VoiceProfile(rate=0.5)}
        mv = MultiVoiceTTSBackend("d.onnx", profiles)
        with _patch_piper():
            mv.synthesize(SpeechEvent("1", "Devagar", "leeento",
                                      voice=VoiceParams(rate=1.2)))
        ev = _FakePiper.instances[0].calls[0]
        self.assertAlmostEqual(ev.voice.rate, 1.2 * 0.5)

    def test_pitch_shift_injected_into_prosody(self):
        profiles = {"Grave": VoiceProfile(pitch_shift=-4.0)}
        mv = MultiVoiceTTSBackend("d.onnx", profiles)
        self.assertEqual(mv.prosody.character_pitch.get("Grave"), -4.0)

    def test_backend_id_varies_with_profiles(self):
        a = MultiVoiceTTSBackend("d.onnx", {"X": VoiceProfile(model_path="a.onnx")})
        b = MultiVoiceTTSBackend("d.onnx", {"X": VoiceProfile(model_path="b.onnx")})
        self.assertNotEqual(a.backend_id, b.backend_id)


if __name__ == "__main__":
    unittest.main()
