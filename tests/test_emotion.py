"""Sistema de ATUAÇÃO — EmotionPolicy, inferência de emoção, persona. Stdlib."""

import unittest

from k_nar.emotion import EmotionPolicy, EmotionShift
from k_nar.narrative.acting import (Persona, SceneMood, infer_emotion,
                                    personas_from_prose)
from k_nar.prosody import ProsodyPolicy


class TestEmotionPolicy(unittest.TestCase):
    def test_neutral_is_rest(self):
        s = EmotionPolicy().resolve("neutro", 1.0)
        self.assertEqual(s.rate_mult, 1.0)
        self.assertEqual(s.pitch_semitones, 0.0)

    def test_fear_is_higher_and_faster(self):
        s = EmotionPolicy().resolve("medo", 1.0)
        self.assertGreater(s.pitch_semitones, 0.0)   # medo = agudo
        self.assertGreater(s.rate_mult, 1.0)         # e mais rápido

    def test_sadness_is_lower_slower_quieter(self):
        s = EmotionPolicy().resolve("tristeza", 1.0)
        self.assertLess(s.pitch_semitones, 0.0)
        self.assertLess(s.rate_mult, 1.0)
        self.assertLess(s.gain_db, 0.0)

    def test_anger_is_louder(self):
        self.assertGreater(EmotionPolicy().resolve("raiva", 1.0).gain_db, 2.0)

    def test_intensity_scales_the_gesture(self):
        pol = EmotionPolicy()
        weak = pol.resolve("medo", 0.2)
        strong = pol.resolve("medo", 1.0)
        self.assertLess(weak.pitch_semitones, strong.pitch_semitones)

    def test_aliases_and_unknown(self):
        pol = EmotionPolicy()
        self.assertEqual(pol.resolve("fear", 1.0), pol.resolve("medo", 1.0))
        self.assertEqual(pol.resolve("xyz", 1.0), pol.resolve("neutro", 1.0))


class TestEmotionProsody(unittest.TestCase):
    def test_emotion_moves_the_bundle(self):
        pol = ProsodyPolicy()
        base = pol.resolve(0.3, emotion="neutro")
        medo = pol.resolve(0.3, emotion="medo", intensity=1.0)
        self.assertGreater(medo.pitch_semitones, base.pitch_semitones)   # medo sobe o pitch
        self.assertLess(medo.length_scale, base.length_scale)            # e acelera

    def test_arousal_floor(self):
        # urgência implica um piso de tensão mesmo com tension baixa
        pol = ProsodyPolicy()
        calm = pol.resolve(0.0, emotion="neutro")
        urgent = pol.resolve(0.0, emotion="urgencia", intensity=1.0)
        self.assertGreater(urgent.gain_db, calm.gain_db)


class TestInference(unittest.TestCase):
    def test_scream_is_urgent_or_angry(self):
        emo, inten = infer_emotion("CORRE! Eles vem ai!", cue="gritou", lang="pt")
        self.assertIn(emo, ("urgencia", "raiva"))
        self.assertGreater(inten, 0.5)

    def test_fear_keyword(self):
        emo, _ = infer_emotion("Eu estava apavorado com aquele silencio.", lang="pt")
        self.assertIn(emo, ("medo", "suspense"))

    def test_ellipsis_is_suspense(self):
        emo, _ = infer_emotion("Eu nao sei se devia...", lang="pt")
        self.assertEqual(emo, "suspense")

    def test_neutral_without_signal(self):
        emo, inten = infer_emotion("Ele assinou o formulario.", lang="pt")
        self.assertEqual(emo, "neutro")
        self.assertLess(inten, 0.5)

    def test_scene_tension_biases_suspense(self):
        calm = infer_emotion("Ele olhou pela janela.", scene_tension=0.0, lang="pt")
        tense = infer_emotion("Ele olhou pela janela.", scene_tension=0.9, lang="pt")
        self.assertGreaterEqual(tense[1], calm[1])   # cena tensa sobe a carga

    def test_reaction_escalates(self):
        cold = infer_emotion("Nao sei.", prev_emotion="neutro", lang="pt")
        hot = infer_emotion("Nao sei.", prev_emotion="medo", lang="pt")
        self.assertGreaterEqual(hot[1], cold[1])


class TestPersona(unittest.TestCase):
    def test_nervous_more_intense_than_calm(self):
        nervous = infer_emotion("Tem alguem ai?", persona=Persona(1.25, "medo", 0.6), lang="pt")
        calm = infer_emotion("Tem alguem ai?", persona=Persona(0.8), lang="pt")
        self.assertGreater(nervous[1], calm[1])

    def test_personas_from_prose(self):
        prose = "O nervoso Renê tremia. Renê olhou em volta. A calma Alzira sorriu."
        p = personas_from_prose(["Renê", "Alzira"], prose, "pt")
        self.assertGreater(p["Renê"].intensity_scale, 1.0)
        self.assertLess(p["Alzira"].intensity_scale, 1.0)


class TestSceneMood(unittest.TestCase):
    def test_rises_then_decays(self):
        mood = SceneMood()
        mood.update("urgencia", 1.0)
        high = mood.value
        self.assertGreater(high, 0.5)
        mood.update("neutro", 0.0)
        self.assertLess(mood.value, high)   # decai quando a cena esfria


if __name__ == "__main__":
    unittest.main()
