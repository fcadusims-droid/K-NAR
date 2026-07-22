"""Testes do forced alignment — stdlib puro, sem numpy/piper.

Constrói `Alignment` à mão (como se viesse do Piper) e exercita a decisão do
corte: preferência por fronteira de palavra/pontuação, respeito ao piso e à
janela, transformações (scaled/trimmed) e o fallback quando não há fronteira.
"""

import unittest

from k_nar.align import Alignment, PhonemeSpan


class _FakePiperAlign:
    """Imita AudioChunk.phoneme_alignments[i] (só .phoneme e .num_samples)."""

    def __init__(self, phoneme, num_samples):
        self.phoneme = phoneme
        self.num_samples = num_samples


class TestAlignmentConstruction(unittest.TestCase):
    def test_from_piper_accumulates_offsets(self):
        raw = [_FakePiperAlign("a", 100), _FakePiperAlign(" ", 50),
               _FakePiperAlign("b", 200)]
        al = Alignment.from_piper(raw, sample_rate=22050)
        self.assertEqual(len(al.spans), 3)
        self.assertEqual(al.spans[0], PhonemeSpan("a", 0, 100))
        self.assertEqual(al.spans[1], PhonemeSpan(" ", 100, 150))
        self.assertEqual(al.spans[2], PhonemeSpan("b", 150, 350))
        self.assertEqual(al.length, 350)

    def test_from_piper_skips_zero_length(self):
        raw = [_FakePiperAlign("a", 100), _FakePiperAlign("x", 0),
               _FakePiperAlign("b", 100)]
        al = Alignment.from_piper(raw, 22050)
        self.assertEqual(len(al.spans), 2)
        self.assertEqual(al.length, 200)

    def test_bool_empty(self):
        self.assertFalse(Alignment())
        self.assertTrue(Alignment([PhonemeSpan("a", 0, 10)]))


class TestBoundaryWeights(unittest.TestCase):
    def test_punct_beats_word_beats_phoneme(self):
        self.assertGreater(PhonemeSpan(".", 0, 1).boundary_weight,
                           PhonemeSpan(" ", 0, 1).boundary_weight)
        self.assertGreater(PhonemeSpan(" ", 0, 1).boundary_weight,
                           PhonemeSpan("k", 0, 1).boundary_weight)

    def test_piper_boundary_marks_are_word_level(self):
        self.assertTrue(PhonemeSpan("^", 0, 1).is_word_gap)
        self.assertTrue(PhonemeSpan("$", 0, 1).is_word_gap)


class TestSnap(unittest.TestCase):
    def _align(self):
        # "a b" com um vale de palavra em 100 e pontuação em 300
        return Alignment([
            PhonemeSpan("a", 0, 100),
            PhonemeSpan(" ", 100, 150),   # fronteira de palavra em 100
            PhonemeSpan("b", 150, 300),
            PhonemeSpan(".", 300, 360),   # pontuação em 300
            PhonemeSpan("c", 360, 500),
        ], sample_rate=1000)

    def test_snaps_to_word_boundary_over_phoneme(self):
        al = self._align()
        # alvo 160 (dentro de "b"): fronteiras candidatas na janela ±80 são 100
        # (palavra) e 150 (fonema). A de palavra vence mesmo estando mais longe.
        sample, kind = al.snap(target=160, window=80, floor=0)
        self.assertEqual(sample, 100)
        self.assertEqual(kind, "palavra")

    def test_punctuation_wins_when_in_window(self):
        al = self._align()
        sample, kind = al.snap(target=320, window=80, floor=0)
        self.assertEqual(sample, 300)
        self.assertEqual(kind, "pontuacao")

    def test_floor_blocks_early_cut(self):
        al = self._align()
        # alvo 160, mas piso 200 proíbe cortar antes -> a fronteira 100/150 fica
        # fora; sobra só 300 (dentro de janela grande).
        sample, kind = al.snap(target=160, window=200, floor=200)
        self.assertEqual(sample, 300)

    def test_no_boundary_in_window_returns_raw(self):
        al = self._align()
        # janela minúscula ao redor de 250 (meio de "b"): nenhuma fronteira -> cru
        sample, kind = al.snap(target=250, window=5, floor=0)
        self.assertEqual(sample, 250)
        self.assertEqual(kind, "cru")

    def test_ties_pick_nearest(self):
        al = Alignment([
            PhonemeSpan("a", 0, 100),
            PhonemeSpan("b", 100, 200),   # fonema em 100
            PhonemeSpan("c", 200, 300),   # fonema em 200
        ], sample_rate=1000)
        # alvo 130: 100 e 200 são ambos fonema (mesmo peso) -> escolhe o mais perto (100)
        sample, kind = al.snap(target=130, window=100, floor=0)
        self.assertEqual(sample, 100)


class TestTransforms(unittest.TestCase):
    def test_scaled_scales_indices(self):
        al = Alignment([PhonemeSpan("a", 0, 100), PhonemeSpan("b", 100, 200)], 1000)
        s = al.scaled(0.5)
        self.assertEqual(s.spans[0], PhonemeSpan("a", 0, 50))
        self.assertEqual(s.spans[1], PhonemeSpan("b", 50, 100))

    def test_scaled_identity(self):
        al = Alignment([PhonemeSpan("a", 0, 100)], 1000)
        self.assertEqual(al.scaled(1.0).spans, al.spans)

    def test_trimmed_shifts_and_clips(self):
        al = Alignment([
            PhonemeSpan("pad", 0, 40),
            PhonemeSpan("a", 40, 140),
            PhonemeSpan("b", 140, 240),
            PhonemeSpan("pad2", 240, 300),
        ], 1000)
        # removeu 40 do início, novo comprimento 200 (cortou 60 do fim)
        t = al.trimmed(lead=40, new_length=200)
        # "pad" (0..40) some; "a" vira 0..100; "b" vira 100..200; "pad2" fora
        labels = [(s.phoneme, s.start, s.end) for s in t.spans]
        self.assertIn(("a", 0, 100), labels)
        self.assertIn(("b", 100, 200), labels)
        self.assertNotIn("pad2", [s.phoneme for s in t.spans])


if __name__ == "__main__":
    unittest.main()
