"""Distância (ProximityPolicy) e espaço acústico. Stdlib + numpy."""

import unittest

from k_nar.narrative import RuleBasedScreenwriter
from k_nar.narrative.lexicons import get_lexicon
from k_nar.proximity import ProximityPolicy

try:
    import numpy as np
    _HAS_NUMPY = True
except Exception:  # pragma: no cover
    _HAS_NUMPY = False


class TestProximityPolicy(unittest.TestCase):
    def test_far_is_quieter_and_muffled_and_central(self):
        pp = ProximityPolicy()
        perto, media, longe = pp.resolve("perto"), pp.resolve("media"), pp.resolve("longe")
        self.assertGreater(perto.gain_db, media.gain_db)
        self.assertLess(longe.gain_db, media.gain_db)
        self.assertGreater(longe.lowpass_hz, 0)        # longe abafa (passa-baixa)
        self.assertEqual(media.lowpass_hz, 0)          # media não filtra
        self.assertLess(longe.pan_scale, 1.0)          # longe puxa p/ o centro
        self.assertGreater(perto.pan_scale, 1.0)       # perto alarga

    def test_aliases_and_default(self):
        pp = ProximityPolicy()
        self.assertEqual(pp.resolve("distante"), pp.resolve("longe"))
        self.assertEqual(pp.resolve("desconhecido"), pp.resolve("media"))


class TestDistanceDetection(unittest.TestCase):
    def _dist(self, text, lang="pt"):
        return RuleBasedScreenwriter._distance_of(text, get_lexicon(lang))

    def test_far_cues(self):
        self.assertEqual(self._dist("Tiros ecoaram ao longe."), "longe")
        self.assertEqual(self._dist("Uma luz no horizonte."), "muito_longe")
        self.assertEqual(self._dist("Gunshots in the distance.", "en"), "longe")

    def test_near_cues(self):
        self.assertEqual(self._dist("Um tiro à queima-roupa."), "perto")
        self.assertEqual(self._dist("Passos bem perto."), "perto")

    def test_default_media(self):
        self.assertEqual(self._dist("Um tiro disparou."), "media")

    def test_sfx_element_carries_distance(self):
        sc = RuleBasedScreenwriter().write("Tiros soaram ao longe.", lang="pt")
        sfx = next(e for e in sc["elementos"] if e["tipo"] == "sfx")
        self.assertEqual(sfx.get("distancia"), "longe")


class TestOrchestratorProximity(unittest.TestCase):
    def test_far_sfx_gets_lowpass_and_lower_gain(self):
        from k_nar.models import Scene, SfxEvent, SpeechEvent
        from k_nar.orchestrator import Orquestrador
        from k_nar.tts.base import RenderedClip
        from k_nar.tts.mock import MockTTSBackend
        scene = Scene(id="c", ambiance="seco", events=[
            SpeechEvent(id="d", character="A", text="olha la"),
            SfxEvent(id="s", tag="tiro", gain_db=-3.0, distance="longe"),
        ])
        clips = {"d": RenderedClip("d", 800, samples=[0.0]),
                 "s": RenderedClip("s", 500, samples=[0.0])}
        tl = Orquestrador(MockTTSBackend()).render_scene(scene, clips=clips)
        s = next(p for p in tl.placements if p.event_id == "s")
        self.assertEqual(s.distance, "longe")
        self.assertGreater(s.lowpass_hz, 0)
        self.assertLess(s.gain_db, -3.0)               # ganho caiu com a distância


class TestSpaceDetection(unittest.TestCase):
    def test_warehouse_sets_reverb(self):
        sc = RuleBasedScreenwriter().write("Entraram no galpão vazio.", ambiance="seco", lang="pt")
        self.assertEqual(sc["ambientacao"], "galpao_vazio")

    def test_common_room_no_false_trigger(self):
        sc = RuleBasedScreenwriter().write("Uma noite na sala de estar.", ambiance="seco", lang="pt")
        self.assertEqual(sc["ambientacao"], "seco")

    def test_explicit_ambiance_respected(self):
        # se o autor fixou a ambiência, não sobrescreve
        sc = RuleBasedScreenwriter().write("Entraram no galpão.", ambiance="catedral", lang="pt")
        self.assertEqual(sc["ambientacao"], "catedral")


@unittest.skipUnless(_HAS_NUMPY, "numpy ausente")
class TestLowpassDSP(unittest.TestCase):
    def test_lowpass_attenuates_highs(self):
        from k_nar.render import dsp
        sr = 22050
        t = np.arange(sr) / sr
        high = np.sin(2 * np.pi * 8000 * t).astype(np.float32)   # tom agudo
        out = dsp.lowpass_1pole(high, 1000.0, sr)                # corta bem abaixo
        self.assertLess(float(np.max(np.abs(out))), 0.5)         # agudo bem atenuado

    def test_no_cutoff_is_passthrough(self):
        from k_nar.render import dsp
        x = np.array([0.1, -0.2, 0.3], dtype=np.float32)
        self.assertTrue(np.array_equal(dsp.lowpass_1pole(x, 0, 22050), x))


@unittest.skipUnless(_HAS_NUMPY, "numpy ausente")
class TestImpulsePresets(unittest.TestCase):
    def test_new_space_presets_exist(self):
        from k_nar.render.impulse import make_impulse_response
        for name in ("galpao_vazio", "catedral", "caverna", "banheiro", "tunel"):
            ir = make_impulse_response(name, 22050)
            self.assertGreater(len(ir), 0)
        # galpão tem cauda MAIS longa que um quarto pequeno
        self.assertGreater(len(make_impulse_response("galpao_vazio", 22050)),
                           len(make_impulse_response("quarto_pequeno", 22050)))


if __name__ == "__main__":
    unittest.main()
