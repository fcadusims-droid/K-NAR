"""Material do foley (superfície + calçado) → timbre + nível. Stdlib."""

import unittest

from k_nar.material import MaterialPolicy
from k_nar.models import Scene, SfxEvent
from k_nar.narrative import RuleBasedScreenwriter
from k_nar.orchestrator import Orquestrador
from k_nar.tts.base import RenderedClip
from k_nar.tts.mock import MockTTSBackend


class TestMaterialPolicy(unittest.TestCase):
    def test_hard_surface_bright_and_loud(self):
        g, lp = MaterialPolicy().resolve("concreto")
        self.assertGreater(g, 0.0)     # duro soca um pouco mais
        self.assertEqual(lp, 0.0)      # brilhante: sem passa-baixa

    def test_soft_surface_muffled_and_quiet(self):
        g, lp = MaterialPolicy().resolve("tapete")
        self.assertLess(g, 0.0)        # macio: mais baixo
        self.assertGreater(lp, 0.0)    # abafa (passa-baixa)

    def test_boot_louder_than_slipper(self):
        gb, _ = MaterialPolicy().resolve("bota")
        gc, _ = MaterialPolicy().resolve("chinelo")
        self.assertGreater(gb, gc)

    def test_combines_footwear_and_surface(self):
        g, lp = MaterialPolicy().resolve("bota madeira")
        self.assertAlmostEqual(g, 2.0)       # bota +2, madeira +0
        self.assertEqual(lp, 6500.0)         # madeira abafa levemente

    def test_gain_clamped(self):
        g, _ = MaterialPolicy().resolve("descalco tapete carpete")  # somaria < -8
        self.assertGreaterEqual(g, -8.0)

    def test_unknown_material_is_neutral(self):
        self.assertEqual(MaterialPolicy().resolve("xyz"), (0.0, 0.0))
        self.assertEqual(MaterialPolicy().resolve(""), (0.0, 0.0))


class TestScreenwriterMaterial(unittest.TestCase):
    def test_detects_footwear_and_surface(self):
        sc = RuleBasedScreenwriter().write(
            "Os passos de bota ecoaram no assoalho de madeira.", narrator=False, lang="pt")
        sfx = next(e for e in sc["elementos"] if e["tipo"] == "sfx")
        self.assertEqual(sfx["tag"], "passos")
        self.assertIn("bota", sfx["material"])
        self.assertIn("madeira", sfx["material"])

    def test_english_material(self):
        sc = RuleBasedScreenwriter().write(
            "Footsteps thudded on the wooden floor.", narrator=False, lang="en")
        sfx = next(e for e in sc["elementos"] if e["tipo"] == "sfx")
        self.assertEqual(sfx.get("material"), "madeira")


class TestOrchestratorMaterial(unittest.TestCase):
    def test_material_adjusts_gain_and_lowpass(self):
        scene = Scene(id="c", ambiance="seco", events=[
            SfxEvent(id="soft", tag="passos", gain_db=0.0, material="descalco tapete"),
            SfxEvent(id="hard", tag="passos", gain_db=0.0, material="bota concreto"),
        ])
        clips = {"soft": RenderedClip("soft", 500, samples=[0.0]),
                 "hard": RenderedClip("hard", 500, samples=[0.0])}
        tl = Orquestrador(MockTTSBackend()).render_scene(scene, clips=clips)
        soft = next(p for p in tl.placements if p.event_id == "soft")
        hard = next(p for p in tl.placements if p.event_id == "hard")
        self.assertLess(soft.gain_db, hard.gain_db)     # descalço/tapete << bota/concreto
        self.assertGreater(soft.lowpass_hz, 0)          # macio abafa
        self.assertEqual(hard.lowpass_hz, 0)            # duro é brilhante


if __name__ == "__main__":
    unittest.main()
