"""Screenwriter multilíngue (EN/ES) e smoke do pipeline/CLI. Stdlib + numpy."""

import unittest

from k_nar.narrative import RuleBasedScreenwriter

try:
    import numpy  # noqa: F401
    _HAS_NUMPY = True
except Exception:  # pragma: no cover
    _HAS_NUMPY = False


def _sw(prose, lang):
    return RuleBasedScreenwriter().write(prose, lang=lang)


class TestScreenwriterEnglish(unittest.TestCase):
    def test_english_dialogue_and_speaker(self):
        out = _sw('"Run!", shouted John.', "en")
        fala = next(e for e in out["elementos"] if e["tipo"] == "fala")
        self.assertEqual(fala["personagem"], "John")
        self.assertEqual(fala["deixa"], "shouted")

    def test_english_sfx_and_ambience(self):
        out = _sw("The forest was dark. A gunshot echoed.", "en")
        tipos = {e["tipo"]: e.get("tag") for e in out["elementos"]}
        self.assertIn("ambiencia", tipos)
        self.assertEqual(tipos["ambiencia"], "floresta_noite")
        sfx = [e for e in out["elementos"] if e["tipo"] == "sfx"]
        self.assertEqual(sfx[0]["tag"], "tiro")


class TestScreenwriterSpanish(unittest.TestCase):
    def test_spanish_dialogue_and_speaker(self):
        out = _sw('"Corran!", grito Ana.', "es")
        fala = next(e for e in out["elementos"] if e["tipo"] == "fala")
        self.assertEqual(fala["personagem"], "Ana")
        self.assertEqual(fala["deixa"], "grito")

    def test_spanish_sfx(self):
        out = _sw("Un trueno sono a lo lejos.", "es")
        sfx = [e for e in out["elementos"] if e["tipo"] == "sfx"]
        self.assertTrue(sfx)
        self.assertEqual(sfx[0]["tag"], "trovao")


@unittest.skipUnless(_HAS_NUMPY, "numpy ausente")
class TestPipelineSmoke(unittest.TestCase):
    def test_render_story_with_formant_fallback(self):
        # sem modelos Piper (models_dir inexistente) -> voz formante; SFX procedural.
        from k_nar.pipeline import render_story
        from k_nar.story import parse_story
        story = parse_story('A floresta escura. "Ola?", disse Ana. Um tiro soou.')
        res = render_story(story, models_dir="/nao/existe")
        self.assertEqual(res.voice_kind, "formante")
        self.assertEqual(res.stereo.shape[0], 2)
        self.assertGreater(res.stereo.shape[1], 0)
        # a cena tem diálogo, SFX e ambiência
        tracks = {p.track for p in res.timeline.placements}
        self.assertIn("dialogo", tracks)
        self.assertIn("sfx", tracks)
        self.assertIn("ambiencia", tracks)


class TestCLIArgs(unittest.TestCase):
    def test_missing_file_returns_error(self):
        from k_nar.cli import main
        self.assertEqual(main(["/nao/existe/historia.md"]), 2)

    def test_parser_flags(self):
        from k_nar.cli import build_parser
        args = build_parser().parse_args(["h.md", "--sem-narrador", "--idioma", "en"])
        self.assertFalse(args.narrador)
        self.assertEqual(args.idioma, "en")


if __name__ == "__main__":
    unittest.main()
