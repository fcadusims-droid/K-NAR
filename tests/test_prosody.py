"""Testes da matriz de prosódia: tensão -> manipuladores acústicos monotônicos."""

from __future__ import annotations

import unittest

from k_nar import ProsodyPolicy


class TestProsodyPolicy(unittest.TestCase):
    def setUp(self):
        self.p = ProsodyPolicy()

    def test_tensao_alta_acelera_e_sobe_pitch_e_ganho(self):
        calmo = self.p.resolve(0.0)
        tenso = self.p.resolve(1.0)
        self.assertLess(tenso.length_scale, calmo.length_scale)     # tenso = mais rápido
        self.assertGreater(tenso.pitch_semitones, calmo.pitch_semitones)  # mais agudo
        self.assertGreater(tenso.gain_db, calmo.gain_db)            # mais alto
        self.assertGreater(tenso.noise_w, calmo.noise_w)           # mais variação

    def test_monotonico_na_tensao(self):
        durs = [self.p.resolve(t).length_scale for t in (0.0, 0.3, 0.6, 1.0)]
        self.assertEqual(durs, sorted(durs, reverse=True))  # length_scale só cai

    def test_rotulo_e_numero_equivalentes(self):
        self.assertAlmostEqual(ProsodyPolicy.tension_scalar(0.8),
                               ProsodyPolicy.tension_scalar("alta"))

    def test_rate_afeta_length_scale(self):
        lento = self.p.resolve(0.5, rate=0.8).length_scale
        rapido = self.p.resolve(0.5, rate=1.25).length_scale
        self.assertGreater(lento, rapido)  # rate maior => length_scale menor

    def test_pitch_distinto_por_personagem(self):
        pa = self.p.resolve(0.5, character="Alien A").pitch_semitones
        pb = self.p.resolve(0.5, character="Alien B").pitch_semitones
        self.assertNotEqual(pa, pb)  # timbres separados a partir de um só modelo

    def test_character_pitch_explicito(self):
        p = ProsodyPolicy(character_pitch={"Narrador": 0.0})
        self.assertEqual(p.resolve(0.5, character="Narrador").pitch_semitones,
                         p.resolve(0.5).pitch_semitones)


if __name__ == "__main__":
    unittest.main(verbosity=2)
