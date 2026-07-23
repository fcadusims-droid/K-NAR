"""Pessoa narrativa (1ª vs 3ª) — detecção e efeito no palco espacial. Stdlib."""

import unittest

from k_nar.narrative import detect_person, resolve_person
from k_nar.narrative.person import PRIMEIRA, TERCEIRA


class TestDetectPerson(unittest.TestCase):
    def test_first_person_pt(self):
        n = "Eu entrei na cozinha. Meu coracao batia. Eu vi a porta e me assustei."
        self.assertEqual(detect_person(n, "pt"), PRIMEIRA)

    def test_third_person_pt(self):
        n = "Herman entrou na cozinha. O coracao dele batia. Ele viu a porta."
        self.assertEqual(detect_person(n, "pt"), TERCEIRA)

    def test_first_person_en(self):
        self.assertEqual(detect_person("I walked in. My heart raced. I saw it.", "en"), PRIMEIRA)

    def test_third_person_en(self):
        self.assertEqual(detect_person("He walked in. His heart raced.", "en"), TERCEIRA)

    def test_empty_defaults_third(self):
        self.assertEqual(detect_person("", "pt"), TERCEIRA)

    def test_spanish_article_not_counted_as_third(self):
        # "el" (artigo) é comum em qualquer pessoa; não deve empurrar p/ 3ª
        n = "Yo entre en la cocina. Mi corazon latia. Yo vi el reloj en el muro."
        self.assertEqual(detect_person(n, "es"), PRIMEIRA)


class TestResolvePerson(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(resolve_person("1"), PRIMEIRA)
        self.assertEqual(resolve_person("primeira"), PRIMEIRA)
        self.assertEqual(resolve_person("eu"), PRIMEIRA)
        self.assertEqual(resolve_person("3"), TERCEIRA)
        self.assertEqual(resolve_person("narrador"), TERCEIRA)
        self.assertEqual(resolve_person("qualquer"), "auto")
        self.assertEqual(resolve_person(""), "auto")


class TestMarkdownStripping(unittest.TestCase):
    def test_html_comments_removed(self):
        # comentários <!-- --> são NOTAS, não prosa: não podem ser lidos em voz alta
        from k_nar.story import strip_markdown
        out = strip_markdown("<!-- nota interna EMOÇÃO -->\nHerman entrou na sala.")
        self.assertNotIn("EMOÇÃO", out)
        self.assertNotIn("nota", out)
        self.assertIn("Herman", out)


class TestTemplatesParseClean(unittest.TestCase):
    def test_example_templates_have_no_comment_leak(self):
        import os
        from k_nar.narrative import RuleBasedScreenwriter
        from k_nar.story import load_story
        base = os.path.join(os.path.dirname(__file__), "..", "examples")
        for name in ("template_terceira_pessoa.md", "template_primeira_pessoa.md"):
            st = load_story(os.path.join(base, name))
            sc = RuleBasedScreenwriter().write(st.prose, narrator=st.narrator, lang=st.lang)
            speakers = {e.get("personagem") for e in sc["elementos"] if e.get("tipo") == "fala"}
            # nenhum locutor genérico "Personagem" (atribuição sempre nomeada) nem vazamento
            self.assertNotIn("Personagem", speakers, f"{name}: fala sem nome")
            for leak in ("EMOÇÃO", "TEMPLATE", "NAR"):
                self.assertNotIn(leak, speakers, f"{name}: comentário vazou")


class TestStoryFrontmatter(unittest.TestCase):
    def test_parses_person_and_protagonist(self):
        from k_nar.story import parse_story
        txt = ("---\npessoa: primeira\nprotagonista: Mateus\n---\n"
               "Eu andei ate a porta.")
        st = parse_story(txt)
        self.assertEqual(st.person, "primeira")
        self.assertEqual(st.protagonist, "Mateus")


if __name__ == "__main__":
    unittest.main()
