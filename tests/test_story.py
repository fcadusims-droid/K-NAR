"""Leitor de história (front-matter + Markdown) e registro de idiomas. Stdlib."""

import unittest

from k_nar.lang import get_language
from k_nar.narrative.lexicons import get_lexicon
from k_nar.story import Story, parse_story, strip_markdown


class TestFrontmatter(unittest.TestCase):
    def test_parses_options(self):
        text = ("---\n"
                "titulo: Minha Historia\n"
                "idioma: en\n"
                "narrador: nao\n"
                "ambientacao: floresta_noite\n"
                "---\n"
                "Era uma vez.")
        s = parse_story(text)
        self.assertEqual(s.title, "Minha Historia")
        self.assertEqual(s.lang, "en")
        self.assertFalse(s.narrator)
        self.assertEqual(s.ambiance, "floresta_noite")
        self.assertEqual(s.prose, "Era uma vez.")

    def test_no_frontmatter_is_plain_prose(self):
        s = parse_story("So a prosa aqui.")
        self.assertEqual(s.prose, "So a prosa aqui.")
        self.assertEqual(s.lang, "pt")       # default
        self.assertTrue(s.narrator)          # default

    def test_narrator_bool_variants(self):
        self.assertTrue(parse_story("---\nnarrador: sim\n---\nx").narrator)
        self.assertTrue(parse_story("---\nnarrator: yes\n---\nx").narrator)
        self.assertTrue(parse_story("---\nnarrador: com\n---\nx").narrator)
        self.assertFalse(parse_story("---\nnarrador: nao\n---\nx").narrator)
        self.assertFalse(parse_story("---\nnarrator: false\n---\nx").narrator)
        self.assertFalse(parse_story("---\nnarrador: sem\n---\nx").narrator)

    def test_english_keys(self):
        s = parse_story("---\ntitle: T\nlanguage: es\n---\nHola.")
        self.assertEqual(s.lang, "es")
        self.assertEqual(s.title, "T")

    def test_crlf_frontmatter(self):
        # arquivos de Windows/web usam \r\n; o front-matter deve casar mesmo assim
        s = parse_story("---\r\nidioma: en\r\nnarrador: nao\r\n---\r\nHello there.")
        self.assertEqual(s.lang, "en")
        self.assertFalse(s.narrator)
        self.assertEqual(s.prose, "Hello there.")

    def test_scene_id_slug(self):
        self.assertEqual(Story(title="A Ponte de Comando!", prose="x").scene_id,
                         "a_ponte_de_comando")


class TestStripMarkdown(unittest.TestCase):
    def test_removes_headers_and_emphasis(self):
        md = ("# Titulo\n\n"
              "Um paragrafo com **negrito** e _italico_.\n\n"
              "## Secao\n"
              "- item de lista\n"
              "> citacao\n")
        out = strip_markdown(md)
        self.assertNotIn("#", out)
        self.assertNotIn("**", out)
        self.assertIn("negrito", out)
        self.assertIn("italico", out)
        self.assertIn("item de lista", out)
        self.assertNotIn(">", out)

    def test_links_become_text(self):
        self.assertIn("clique aqui", strip_markdown("[clique aqui](http://x.com)"))
        self.assertNotIn("http", strip_markdown("[clique aqui](http://x.com)"))

    def test_code_fences_removed(self):
        out = strip_markdown("antes\n```\ncodigo();\n```\ndepois")
        self.assertNotIn("codigo", out)
        self.assertIn("antes", out)
        self.assertIn("depois", out)


class TestLanguageRegistry(unittest.TestCase):
    def test_aliases_resolve(self):
        for alias in ("en", "en_US", "english", "ingles"):
            self.assertEqual(get_language(alias).code, "en_US")
        for alias in ("es", "espanol", "spanish"):
            self.assertEqual(get_language(alias).code, "es_ES")

    def test_default_is_pt(self):
        self.assertEqual(get_language("desconhecido").code, "pt_BR")
        self.assertEqual(get_language("").code, "pt_BR")

    def test_lexicon_matches_language(self):
        self.assertIn("said", get_lexicon("en").speech_verbs)
        self.assertIn("dijo", get_lexicon("es").speech_verbs)
        self.assertIn("disse", get_lexicon("pt").speech_verbs)


if __name__ == "__main__":
    unittest.main()
