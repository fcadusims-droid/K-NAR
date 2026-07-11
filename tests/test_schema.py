"""Testes do validador estrito (portão da fronteira com o LLM)."""

from __future__ import annotations

import unittest

from k_nar import SchemaError, validate_scene


def _cena_valida():
    return {
        "cena_id": "c1",
        "ambientacao": "seco",
        "eventos": [
            {
                "id": "f1", "personagem": "A", "texto": "ola",
                "voz": {"tensao": "alta", "velocidade": 0.9},
                "entrada": {"tipo": "sequencial"},
                "saida": {"pausa": "curta"},
                "palco": {"estereo": -30},
            }
        ],
    }


class TestSchema(unittest.TestCase):
    def test_cena_valida_passa(self):
        validate_scene(_cena_valida())  # nao levanta

    def test_tensao_semantica_invalida_e_recusada(self):
        d = _cena_valida()
        d["eventos"][0]["voz"]["tensao"] = "muito alta"  # variacao do LLM
        with self.assertRaises(SchemaError) as ctx:
            validate_scene(d)
        self.assertTrue(any("tensao" in e for e in ctx.exception.errors))

    def test_tipo_de_entrada_inventado_e_recusado(self):
        d = _cena_valida()
        d["eventos"][0]["entrada"]["tipo"] = "cortar_tudo"
        with self.assertRaises(SchemaError):
            validate_scene(d)

    def test_agressividade_fora_do_intervalo(self):
        d = _cena_valida()
        d["eventos"][0]["entrada"] = {"tipo": "interrupcao", "agressividade": 5.0}
        with self.assertRaises(SchemaError):
            validate_scene(d)

    def test_ids_duplicados(self):
        d = _cena_valida()
        d["eventos"].append(dict(d["eventos"][0]))
        with self.assertRaises(SchemaError):
            validate_scene(d)

    def test_lista_todos_os_erros(self):
        d = {"eventos": [{"id": "x", "entrada": {"tipo": "xyz"}, "saida": {"pausa": "eterna"}}]}
        with self.assertRaises(SchemaError) as ctx:
            validate_scene(d)
        # faltam cena_id/ambientacao/texto/personagem + tipo + pausa invalidos
        self.assertGreaterEqual(len(ctx.exception.errors), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
