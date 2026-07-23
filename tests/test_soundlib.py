"""Catálogo de sons + condicionamento da LibrarySfxBackend. Stdlib + numpy."""

import unittest

from k_nar.sfx.catalog import (AMBIENCE_TAGS, CATALOG, ESC50_CATEGORIES,
                               esc50_category, is_ambience)

try:
    import numpy as np
    _HAS_NUMPY = True
except Exception:  # pragma: no cover
    _HAS_NUMPY = False


class TestCatalog(unittest.TestCase):
    def test_catalog_not_empty(self):
        self.assertGreater(len(CATALOG), 40)

    def test_ambience_and_esc50_helpers(self):
        self.assertTrue(is_ambience("grilos"))
        self.assertFalse(is_ambience("tiro"))
        self.assertEqual(esc50_category("grilos"), "crickets")
        self.assertIsNone(esc50_category("tiro"))       # procedural

    def test_ambience_tags_consistent(self):
        for tag in AMBIENCE_TAGS:
            self.assertTrue(CATALOG[tag].ambience)

    def test_esc50_categories_reverse_map(self):
        # crickets alimenta grilos E floresta_noite
        self.assertIn("grilos", ESC50_CATEGORIES["crickets"])
        self.assertIn("floresta_noite", ESC50_CATEGORIES["crickets"])

    def test_every_procedural_tag_has_generator(self):
        # todo tag SEM sample real (esc50=None) precisa de um gerador procedural,
        # senão não há como renderizá-lo.
        from k_nar.sfx.procedural import _AMBIENCE, _SFX
        gen_tags = set(_SFX) | set(_AMBIENCE)
        for tag, sd in CATALOG.items():
            if sd.esc50 is None:
                self.assertIn(tag, gen_tags, f"tag procedural '{tag}' sem gerador")


@unittest.skipUnless(_HAS_NUMPY, "numpy ausente")
class TestLibraryConditioning(unittest.TestCase):
    def _lib(self, **kw):
        from k_nar.sfx import LibrarySfxBackend
        return LibrarySfxBackend({}, sr=1000, **kw)

    def test_sfx_capped_and_normalized(self):
        lib = self._lib(sfx_max_s=2.5)
        audio = np.ones(5000, dtype=np.float32) * 0.2   # 5s constante em 1000 Hz
        out = lib._condition(audio, "tiro")             # não-ambiência -> capado
        self.assertLessEqual(len(out), int(2.5 * 1000) + 1)
        self.assertAlmostEqual(float(np.max(np.abs(out))), 0.9, places=2)  # normalizado

    def test_ambience_not_capped(self):
        lib = self._lib()
        audio = np.ones(5000, dtype=np.float32) * 0.2
        out = lib._condition(audio, "grilos")           # ambiência -> textura inteira
        self.assertEqual(len(out), 5000)

    def test_falls_back_to_procedural(self):
        from k_nar.sfx import LibrarySfxBackend, ProceduralSfxBackend
        from k_nar.models import SfxEvent
        lib = LibrarySfxBackend({}, sr=22050, fallback=ProceduralSfxBackend(22050))
        clip = lib.render(SfxEvent(id="x", tag="estatica"))   # não está no manifesto
        self.assertGreater(len(clip.samples), 0)


@unittest.skipUnless(_HAS_NUMPY, "numpy ausente")
class TestElectronicSounds(unittest.TestCase):
    def test_new_electronic_tags_render(self):
        from k_nar.models import AmbienceEvent, SfxEvent
        from k_nar.sfx import ProceduralSfxBackend
        be = ProceduralSfxBackend(sr=22050)
        for tag, cls in [("estatica", AmbienceEvent), ("transformador", AmbienceEvent),
                         ("tom_discagem", SfxEvent), ("linha_ocupada", SfxEvent),
                         ("bipe", SfxEvent)]:
            clip = be.render(cls(id="x", tag=tag))
            self.assertGreater(len(clip.samples), 0)
            self.assertTrue(np.all(np.isfinite(clip.samples)))


if __name__ == "__main__":
    unittest.main()
