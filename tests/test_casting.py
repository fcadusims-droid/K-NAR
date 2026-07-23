"""Casting — voz por aparência/idade/gênero inferida da prosa. Stdlib puro."""

import unittest

from k_nar.casting import Traits, cast_voices, infer_traits, voice_for


class TestTraitInference(unittest.TestCase):
    def test_old_man_gravelly(self):
        prose = "O velho Herman, de voz rouca, sentou. Herman suspirou fundo."
        tr = infer_traits(["Herman"], prose, "pt")["Herman"]
        self.assertEqual(tr.gender, "m")
        self.assertEqual(tr.age, "idoso")
        self.assertEqual(tr.register, "grave")

    def test_young_girl_high(self):
        prose = "A menina Sofia riu. Sofia tinha uma voz fina e alegre."
        tr = infer_traits(["Sofia"], prose, "pt")["Sofia"]
        self.assertEqual(tr.gender, "f")
        self.assertEqual(tr.age, "crianca")
        self.assertEqual(tr.register, "agudo")

    def test_no_descriptor_is_neutral(self):
        tr = infer_traits(["Alex"], "Alex entrou. Alex fechou a porta.", "pt")["Alex"]
        self.assertEqual(tr.gender, "?")     # sem descritor: não adivinha gênero
        self.assertEqual(tr.age, "adulto")

    def test_ambiguous_sentence_does_not_cross_attribute(self):
        # frase com DOIS personagens não credita traços a nenhum (evita cross-atribuição)
        prose = "O velho Joao e a menina Ana conversaram."
        tr = infer_traits(["Joao", "Ana"], prose, "pt")
        self.assertEqual(tr["Joao"].age, "adulto")   # 'velho' não foi creditado (ambíguo)
        self.assertEqual(tr["Ana"].age, "adulto")

    def test_english_descriptors(self):
        tr = infer_traits(["Tom"], "Old Tom had a deep, gruff voice. Tom coughed.", "en")["Tom"]
        self.assertEqual(tr.gender, "m")
        self.assertEqual(tr.age, "idoso")
        self.assertEqual(tr.register, "grave")


class TestVoiceMapping(unittest.TestCase):
    def test_old_man_is_low_and_slow(self):
        vp = voice_for(Traits(gender="m", age="idoso", register="grave"), name="X")
        self.assertLess(vp.pitch_shift, -3.0)   # grave
        self.assertLess(vp.rate, 0.95)          # lento

    def test_child_is_high_and_fast(self):
        vp = voice_for(Traits(gender="f", age="crianca", register="agudo"), name="Y")
        self.assertGreater(vp.pitch_shift, 3.0)
        self.assertGreater(vp.rate, 1.0)

    def test_pitch_is_clamped(self):
        vp = voice_for(Traits(gender="f", age="crianca", register="agudo"), name="Zzz")
        self.assertLessEqual(abs(vp.pitch_shift), 7.5)

    def test_same_archetype_differ_by_name(self):
        a = voice_for(Traits(), name="Joana")
        b = voice_for(Traits(), name="Carlos")
        self.assertNotEqual(a.pitch_shift, b.pitch_shift)  # jitter por nome os separa

    def test_jitter_is_deterministic(self):
        self.assertEqual(voice_for(Traits(), name="Rui").pitch_shift,
                         voice_for(Traits(), name="Rui").pitch_shift)


class TestCastVoices(unittest.TestCase):
    def test_narrator_not_cast(self):
        profs = cast_voices(["Herman", "Narrador"], "O velho Herman falou.", "pt")
        self.assertIn("Herman", profs)
        self.assertNotIn("Narrador", profs)   # o narrador tem voz própria no pipeline

    def test_placeholders_skipped(self):
        profs = cast_voices(["?", "Personagem", "Ana"], "A menina Ana riu.", "pt")
        self.assertEqual(set(profs), {"Ana"})


if __name__ == "__main__":
    unittest.main()
