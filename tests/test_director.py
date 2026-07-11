"""Testes do Director por regras (determinístico) e da montagem/validação da base."""

from __future__ import annotations

import unittest

from k_nar import SchemaError
from k_nar.director import RuleBasedDirector


def _script(*falas):
    return {
        "cena_id": "t", "ambientacao": "seco",
        "falas": [{"personagem": p, "texto": t} for p, t in falas],
    }


class TestRuleDirector(unittest.TestCase):
    def setUp(self):
        self.d = RuleBasedDirector()

    def test_saida_valida_no_schema(self):
        scene = self.d.direct(_script(("A", "ola mundo"), ("B", "tudo bem?")))
        self.assertEqual(len(scene["eventos"]), 2)
        # se validate_scene falhasse, direct() teria levantado SchemaError

    def test_grito_vira_tensao_alta_ou_extrema(self):
        scene = self.d.direct(_script(("A", "calma"), ("B", "CHEGA! ACABOU!")))
        self.assertIn(scene["eventos"][1]["voz"]["tensao"], ("alta", "extrema"))

    def test_fala_suspensa_e_interrompida_pela_proxima(self):
        scene = self.d.direct(_script(
            ("A", "eu nao queria que terminasse assim..."),
            ("B", "cale-se!"),
        ))
        self.assertEqual(scene["eventos"][1]["entrada"]["tipo"], "interrupcao")
        self.assertGreater(scene["eventos"][1]["entrada"]["agressividade"], 0.0)

    def test_primeira_fala_nunca_interrompe(self):
        scene = self.d.direct(_script(("A", "GRITO INICIAL!")))
        self.assertEqual(scene["eventos"][0]["entrada"]["tipo"], "sequencial")

    def test_pans_estaveis_por_personagem(self):
        scene = self.d.direct(_script(("A", "um"), ("B", "dois"), ("A", "tres")))
        pans = {e["personagem"]: e["palco"]["estereo"] for e in scene["eventos"]}
        # A aparece 2x com o MESMO pan; A != B
        a_pans = [e["palco"]["estereo"] for e in scene["eventos"] if e["personagem"] == "A"]
        self.assertEqual(a_pans[0], a_pans[1])
        self.assertNotEqual(pans["A"], pans["B"])

    def test_determinismo(self):
        s = _script(("A", "isto e um teste"), ("B", "de novo!"))
        self.assertEqual(self.d.direct(s), RuleBasedDirector().direct(s))

    def test_script_vazio_falha(self):
        with self.assertRaises(ValueError):
            self.d.direct({"cena_id": "x", "ambientacao": "seco", "falas": []})


if __name__ == "__main__":
    unittest.main(verbosity=2)
