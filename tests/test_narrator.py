"""O narrador: segmentação fiel, montagem com pausas e o caminho ponta a ponta."""

import unittest

from k_nar.narrator import (NarrationConfig, build_backend, narrate,
                            segment_script)


class TestSegmentation(unittest.TestCase):
    def test_paragraphs_are_blocks_with_pauses(self):
        # dois parágrafos -> dois blocos; frases dentro do parágrafo NÃO viram blocos
        # (o motor lê o parágrafo inteiro com prosódia contínua).
        text = "Frase um. Frase dois.\n\nOutro parágrafo."
        cfg = NarrationConfig(paragraph_pause_ms=800)
        segs = segment_script(text, cfg)
        self.assertEqual([s.text for s in segs],
                         ["Frase um. Frase dois", "Outro parágrafo"])
        self.assertEqual(segs[0].pause_after_ms, 800)  # pausa entre parágrafos
        self.assertEqual(segs[1].pause_after_ms, 0)    # último: sem pausa (tail cobre)

    def test_terminal_punct_stripped_internal_kept(self):
        # a pontuação do FIM do bloco sai (o XTTS a vocaliza); a interna fica.
        segs = segment_script("O Dr. Silva chegou. Todos aplaudiram!")
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0].text, "O Dr. Silva chegou. Todos aplaudiram")

    def test_ids_are_unique_and_ordered(self):
        segs = segment_script("Um.\n\nDois.\n\nTrês.")
        ids = [s.id for s in segs]
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, sorted(ids))

    def test_empty_text_yields_nothing(self):
        self.assertEqual(segment_script("   \n\n  "), [])


class TestNarrateEndToEnd(unittest.TestCase):
    """Usa o backend formante (sintético, offline) — não baixa torch/coqui."""

    def setUp(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy ausente")

    def test_produces_mono_audio(self):
        backend = build_backend("formante")
        cfg = NarrationConfig(lead_ms=100, tail_ms=200, paragraph_pause_ms=500)
        res = narrate("Primeiro parágrafo aqui.\n\nSegundo.\n\nTerceiro.", backend,
                      config=cfg, workers=1)
        self.assertEqual(res.voice_kind, "formante")
        self.assertEqual(len(res.segments), 3)  # 3 parágrafos -> 3 blocos
        self.assertGreater(res.duration_ms, 0)
        self.assertEqual(res.audio.ndim, 1)  # mono

    def test_pauses_extend_duration(self):
        backend = build_backend("formante")
        text = "Uma frase.\n\nOutra frase."
        short = narrate(text, backend, workers=1,
                        config=NarrationConfig(paragraph_pause_ms=0, lead_ms=0, tail_ms=0))
        backend2 = build_backend("formante")
        longp = narrate(text, backend2, workers=1,
                        config=NarrationConfig(paragraph_pause_ms=2000, lead_ms=0, tail_ms=0))
        self.assertGreater(longp.duration_ms, short.duration_ms + 1500)

    def test_empty_raises(self):
        backend = build_backend("formante")
        with self.assertRaises(ValueError):
            narrate("   ", backend)

    def test_write_wav_is_mono_pcm(self):
        import wave

        backend = build_backend("formante")
        res = narrate("Teste de escrita.", backend, workers=1)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            res.write_wav(f.name)
            with wave.open(f.name, "rb") as w:
                self.assertEqual(w.getnchannels(), 1)
                self.assertEqual(w.getsampwidth(), 2)
                self.assertGreater(w.getnframes(), 0)


class TestBuildBackend(unittest.TestCase):
    def test_unknown_engine_raises(self):
        with self.assertRaises(ValueError):
            build_backend("naoexiste")


if __name__ == "__main__":
    unittest.main()
