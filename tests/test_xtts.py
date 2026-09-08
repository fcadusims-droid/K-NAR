"""XTTSBackend: partes testáveis sem carregar torch/coqui (identidade de voz + split).

O carregamento do modelo (torch) é validado à parte; aqui cobrimos o `backend_id`
(que entra na chave de cache) e a quebra de texto — pura lógica, sem baixar nada.
"""

import unittest

from k_nar.tts.xtts import XTTSBackend, _split_text


class TestBackendIdVoiceIdentity(unittest.TestCase):
    """Regressão: trocar a voz TEM de mudar o backend_id, senão o cache devolve o
    áudio da voz anterior para o mesmo texto."""

    def test_default_vs_clone_differ(self):
        default = XTTSBackend(language="pt").backend_id
        clone = XTTSBackend(language="pt", speaker_wavs={"Narrador": "minha_voz.wav"}).backend_id
        self.assertNotEqual(default, clone)

    def test_two_different_refs_differ(self):
        a = XTTSBackend(language="pt", speaker_wavs={"Narrador": "voz_a.wav"}).backend_id
        b = XTTSBackend(language="pt", speaker_wavs={"Narrador": "voz_b.wav"}).backend_id
        self.assertNotEqual(a, b)

    def test_two_studio_speakers_differ(self):
        a = XTTSBackend(language="pt", speaker="Ana Florence").backend_id
        b = XTTSBackend(language="pt", speaker="Dionisio Schuyler").backend_id
        self.assertNotEqual(a, b)

    def test_same_voice_is_stable(self):
        a = XTTSBackend(language="pt", speaker="Ana Florence").backend_id
        b = XTTSBackend(language="pt", speaker="Ana Florence").backend_id
        self.assertEqual(a, b)

    def test_language_in_id(self):
        self.assertNotEqual(XTTSBackend(language="pt").backend_id,
                            XTTSBackend(language="en").backend_id)


class TestSplitText(unittest.TestCase):
    def test_short_text_single_chunk(self):
        self.assertEqual(_split_text("Uma frase curta."), ["Uma frase curta."])

    def test_long_text_is_split(self):
        long = "Palavra " * 60  # ~480 chars, acima do limite do XTTS
        chunks = _split_text(long)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 180 for c in chunks))

    def test_empty(self):
        self.assertEqual(_split_text("   "), [])


if __name__ == "__main__":
    unittest.main()
