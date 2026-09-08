"""Leitor de roteiro: front-matter, defaults e limpeza de Markdown."""

import unittest

from k_nar.script import Script, parse_script, strip_markdown


class TestParseScript(unittest.TestCase):
    def test_frontmatter_fields(self):
        text = (
            "---\n"
            "titulo: Meu Video\n"
            "idioma: en\n"
            "locutor: Dionisio Schuyler\n"
            "voz_ref: minha_voz.wav\n"
            "velocidade: 1.2\n"
            "pausa_frase: 300\n"
            "pausa_paragrafo: 900\n"
            "---\n"
            "Primeira frase. Segunda frase.\n"
        )
        s = parse_script(text)
        self.assertEqual(s.title, "Meu Video")
        self.assertEqual(s.lang, "en")
        self.assertEqual(s.locutor, "Dionisio Schuyler")
        self.assertEqual(s.voice_ref, "minha_voz.wav")
        self.assertAlmostEqual(s.speed, 1.2)
        self.assertEqual(s.sentence_pause_ms, 300)
        self.assertEqual(s.paragraph_pause_ms, 900)
        self.assertIn("Primeira frase", s.text)

    def test_defaults_without_frontmatter(self):
        s = parse_script("Só o texto, sem cabeçalho.", title="arquivo")
        self.assertEqual(s.title, "arquivo")
        self.assertEqual(s.lang, "pt")
        self.assertEqual(s.locutor, "")
        self.assertEqual(s.voice_ref, "")
        self.assertAlmostEqual(s.speed, 1.0)
        self.assertEqual(s.text, "Só o texto, sem cabeçalho.")

    def test_slug(self):
        self.assertEqual(Script(title="Olá, Mundo!", text="x").slug, "ol_mundo")
        self.assertEqual(Script(title="", text="x").slug, "narracao")


class TestStripMarkdown(unittest.TestCase):
    def test_headers_dropped_prose_kept(self):
        out = strip_markdown("# Título\n\nUm parágrafo real.\n\n## Seção\n\nOutro.")
        self.assertNotIn("Título", out)
        self.assertNotIn("Seção", out)
        self.assertIn("Um parágrafo real.", out)
        self.assertIn("Outro.", out)

    def test_comments_and_emphasis(self):
        out = strip_markdown("Texto <!-- nota interna --> com **ênfase** e _itálico_.")
        self.assertNotIn("nota interna", out)
        self.assertIn("ênfase", out)
        self.assertIn("itálico", out)
        self.assertNotIn("*", out)


if __name__ == "__main__":
    unittest.main()
