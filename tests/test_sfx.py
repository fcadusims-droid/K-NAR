"""Fase 5 — backends de som e ducking. Requer numpy (pula se ausente, como test_render)."""

import unittest

try:
    import numpy as np
    _HAS_NUMPY = True
except Exception:  # pragma: no cover
    _HAS_NUMPY = False

from k_nar.models import AmbienceEvent, SfxEvent


@unittest.skipUnless(_HAS_NUMPY, "numpy ausente")
class TestProceduralSfx(unittest.TestCase):
    def setUp(self):
        from k_nar.sfx import ProceduralSfxBackend
        self.be = ProceduralSfxBackend(sr=22050)

    def test_known_tag_has_audio_and_duration(self):
        clip = self.be.render(SfxEvent(id="s", tag="tiro"))
        self.assertGreater(clip.duration_ms, 0)
        self.assertEqual(clip.sample_rate, 22050)
        self.assertGreater(len(clip.samples), 0)

    def test_deterministic(self):
        a = self.be.render(SfxEvent(id="s", tag="explosao")).samples
        b = self.be.render(SfxEvent(id="s", tag="explosao")).samples
        self.assertTrue(np.array_equal(a, b))

    def test_distinct_tags_differ(self):
        tiro = self.be.render(SfxEvent(id="s", tag="tiro")).samples
        vento = self.be.render(AmbienceEvent(id="a", tag="vento")).samples
        self.assertNotEqual(len(tiro), len(vento))

    def test_unknown_tag_is_audible_blip(self):
        clip = self.be.render(SfxEvent(id="s", tag="tag_inexistente_xyz"))
        self.assertGreater(len(clip.samples), 0)
        self.assertGreater(float(np.max(np.abs(clip.samples))), 0.0)


@unittest.skipUnless(_HAS_NUMPY, "numpy ausente")
class TestLibrarySfx(unittest.TestCase):
    def test_falls_back_to_procedural_when_tag_missing(self):
        from k_nar.sfx import LibrarySfxBackend, ProceduralSfxBackend
        be = LibrarySfxBackend({}, sr=22050, fallback=ProceduralSfxBackend(22050))
        clip = be.render(SfxEvent(id="s", tag="tiro"))
        self.assertGreater(len(clip.samples), 0)   # veio do fallback

    def test_loads_real_wav(self):
        import tempfile
        import wave
        from pathlib import Path
        from k_nar.sfx import LibrarySfxBackend
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "beep.wav"
            n, sr = 4410, 22050
            data = (np.sin(2 * np.pi * 440 * np.arange(n) / sr) * 20000).astype("<i2")
            with wave.open(str(path), "w") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
                w.writeframes(data.tobytes())
            be = LibrarySfxBackend({"beep": [str(path)]}, sr=sr)
            clip = be.render(SfxEvent(id="s", tag="beep"))
            self.assertAlmostEqual(clip.duration_ms, 200, delta=15)
            self.assertGreater(float(np.max(np.abs(clip.samples))), 0.1)


@unittest.skipUnless(_HAS_NUMPY, "numpy ausente")
class TestDucking(unittest.TestCase):
    def test_duck_gain_drops_under_speech(self):
        from k_nar.render.renderer import TimelineRenderer
        r = TimelineRenderer(sr=8000, duck_db=-12.0)
        # fala presente só na metade final -> ducking deve baixar lá, e ~1 no começo
        speech = np.zeros((2, 8000), dtype=np.float32)
        speech[:, 4000:] = 0.8
        gain = r._duck_gain(speech)
        self.assertIsNotNone(gain)
        self.assertGreater(float(gain[500]), 0.9)    # início: sem fala, ganho cheio
        self.assertLess(float(gain[6000]), 0.5)      # fim: sob fala, afundou
        self.assertGreaterEqual(float(gain.min()), 10 ** (-12 / 20) - 1e-3)

    def test_no_speech_returns_none(self):
        from k_nar.render.renderer import TimelineRenderer
        r = TimelineRenderer(sr=8000)
        self.assertIsNone(r._duck_gain(np.zeros((2, 1000), dtype=np.float32)))

    def test_combine_ducks_ambience_vs_naive_sum(self):
        # compara mix com ducking vs soma ingênua: onde há fala, o total (fala +
        # ambiência DUCKADA) deve ser MENOR que fala + ambiência cheia. Sinais
        # positivos p/ o teste ser inequívoco.
        from k_nar.render.renderer import TimelineRenderer
        sr = 8000
        r = TimelineRenderer(sr=sr, duck_db=-12.0)
        n = sr
        speech = np.zeros((2, n), dtype=np.float32); speech[:, n // 2:] = 0.5
        amb = np.full((2, n), 0.3, dtype=np.float32)
        ducked = r._combine_tracks({"dialogo": speech, "ambiencia": amb}, n)
        naive = speech + amb
        # sob a fala (2a metade): ducking abaixou a ambiência -> total menor
        self.assertLess(float(ducked[0, 3 * n // 4]), float(naive[0, 3 * n // 4]))
        # sem fala (início): ambiência cheia -> praticamente igual à soma
        self.assertAlmostEqual(float(ducked[0, 10]), float(naive[0, 10]), places=2)


if __name__ == "__main__":
    unittest.main()
