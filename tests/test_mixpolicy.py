"""MixPolicy (diretor de mix) — níveis de bus por trilha. Stdlib + numpy."""

import unittest

from k_nar.mixpolicy import MixPolicy

try:
    import numpy as np
    _HAS_NUMPY = True
except Exception:  # pragma: no cover
    _HAS_NUMPY = False


class TestMixPolicy(unittest.TestCase):
    def test_level_gain_linear(self):
        m = MixPolicy(track_level_db={"musica": -6.0, "dialogo": 0.0})
        self.assertAlmostEqual(m.level_gain("dialogo"), 1.0)
        self.assertAlmostEqual(m.level_gain("musica"), 10 ** (-6 / 20), places=5)

    def test_unknown_track_is_unity(self):
        self.assertEqual(MixPolicy().level_gain("inexistente"), 1.0)


@unittest.skipUnless(_HAS_NUMPY, "numpy ausente")
class TestMixPolicyInRenderer(unittest.TestCase):
    def test_track_level_attenuates_bus(self):
        from k_nar.render.renderer import TimelineRenderer
        # música a -6 dB: o bed de música no mix sai ~metade da amplitude de entrada,
        # e sem fala não há ducking, então é só o trim de bus.
        mix = MixPolicy(track_level_db={"musica": -6.0}, duck_db=-12.0)
        r = TimelineRenderer(sr=8000, mix=mix)
        n = 4000
        music = np.full((2, n), 0.4, dtype=np.float32)
        out = r._combine_tracks({"musica": music}, n)
        self.assertAlmostEqual(float(out[0, 100]), 0.4 * 10 ** (-6 / 20), places=3)

    def test_duck_db_override_flows_to_policy(self):
        from k_nar.render.renderer import TimelineRenderer
        r = TimelineRenderer(sr=8000, duck_db=-9.0)
        self.assertAlmostEqual(r.duck_db, -9.0)
        self.assertAlmostEqual(r.mix.duck_db, -9.0)


if __name__ == "__main__":
    unittest.main()
