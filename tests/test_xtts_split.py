"""Quebra de texto do XTTS (frases longas estouram a janela do modelo). Stdlib."""

import unittest

from k_nar.tts.xtts import _MAX_CHARS, _split_text


class TestSplitText(unittest.TestCase):
    def test_short_text_is_one_chunk(self):
        self.assertEqual(_split_text("Ola, tudo bem?"), ["Ola, tudo bem?"])

    def test_empty(self):
        self.assertEqual(_split_text("   "), [])

    def test_long_text_is_chunked_under_limit(self):
        long = ("Meu nome e Herman e eu dirijo esta penitenciaria ha muitos anos, " * 8).strip()
        chunks = _split_text(long)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c), _MAX_CHARS)

    def test_splits_on_sentence_then_comma(self):
        txt = ("Primeira frase bem curta. " +
               "Segunda frase muito longa, cheia de virgulas, que precisa ser "
               "quebrada, porque estoura o limite de tokens do modelo neural, entao "
               "cortamos em pedacos menores para caber com folga na janela.")
        chunks = _split_text(txt)
        self.assertGreaterEqual(len(chunks), 2)
        for c in chunks:
            self.assertLessEqual(len(c), _MAX_CHARS)

    def test_no_text_lost(self):
        txt = "Uma frase. Outra frase um pouco maior aqui. E mais uma no final."
        joined = " ".join(_split_text(txt)).replace(" ", "")
        self.assertEqual(joined, txt.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
