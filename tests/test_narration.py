"""Testes da generalização Event + Timeline multitrack (Fase 3) — stdlib puro."""

import unittest

from k_nar.models import (NarrationEvent, Scene, SpeechEvent, Track, build_event)
from k_nar.orchestrator import Orquestrador
from k_nar.schema import SchemaError, validate_scene
from k_nar.tts.mock import MockTTSBackend


class TestEventDispatch(unittest.TestCase):
    def test_build_event_defaults_to_speech(self):
        ev = build_event({"id": "1", "personagem": "Ana", "texto": "oi"})
        self.assertIsInstance(ev, SpeechEvent)
        self.assertEqual(ev.track, Track.DIALOGUE)

    def test_build_event_narration_by_tipo(self):
        ev = build_event({"id": "n1", "tipo_evento": "narracao", "texto": "Era uma vez."})
        self.assertIsInstance(ev, NarrationEvent)
        self.assertEqual(ev.track, Track.NARRATION)
        self.assertEqual(ev.character, "Narrador")

    def test_build_event_narration_by_character(self):
        ev = build_event({"id": "n1", "personagem": "Narrador", "texto": "Era uma vez."})
        self.assertIsInstance(ev, NarrationEvent)

    def test_scene_mixes_narration_and_dialogue(self):
        scene = Scene.from_dict({
            "cena_id": "c", "ambientacao": "seco",
            "eventos": [
                {"id": "n1", "tipo_evento": "narracao", "texto": "A porta abriu."},
                {"id": "d1", "personagem": "Ana", "texto": "Quem esta ai?"},
            ],
        })
        self.assertIsInstance(scene.events[0], NarrationEvent)
        self.assertIsInstance(scene.events[1], SpeechEvent)


class TestMultitrackOrchestration(unittest.TestCase):
    def test_placements_carry_track(self):
        scene = Scene.from_dict({
            "cena_id": "c", "ambientacao": "seco",
            "eventos": [
                {"id": "n1", "tipo_evento": "narracao", "texto": "A porta abriu devagar."},
                {"id": "d1", "personagem": "Ana", "texto": "Quem esta ai dentro?"},
                {"id": "n2", "tipo_evento": "narracao", "texto": "Ninguem respondeu."},
            ],
        })
        tl = Orquestrador(MockTTSBackend()).render_scene(scene)
        tracks = {p.event_id: p.track for p in tl.placements}
        self.assertEqual(tracks["n1"], "narracao")
        self.assertEqual(tracks["d1"], "dialogo")
        self.assertEqual(tracks["n2"], "narracao")

    def test_narration_and_dialogue_are_sequential_in_time(self):
        # narração e diálogo compartilham o cursor: não se sobrepõem no tempo
        scene = Scene.from_dict({
            "cena_id": "c", "ambientacao": "seco",
            "eventos": [
                {"id": "n1", "tipo_evento": "narracao", "texto": "A porta abriu."},
                {"id": "d1", "personagem": "Ana", "texto": "Ola?"},
            ],
        })
        tl = Orquestrador(MockTTSBackend()).render_scene(scene)
        n1 = next(p for p in tl.placements if p.event_id == "n1")
        d1 = next(p for p in tl.placements if p.event_id == "d1")
        self.assertGreaterEqual(d1.start_ms, n1.natural_end_ms)

    def test_to_dict_includes_track(self):
        scene = Scene.from_dict({
            "cena_id": "c", "ambientacao": "seco",
            "eventos": [{"id": "n1", "tipo_evento": "narracao", "texto": "Fim."}],
        })
        tl = Orquestrador(MockTTSBackend()).render_scene(scene)
        self.assertEqual(tl.to_dict()["trilha"][0]["faixa"], "narracao")


class TestSchemaNarration(unittest.TestCase):
    def test_narration_without_personagem_is_valid(self):
        validate_scene({
            "cena_id": "c", "ambientacao": "seco",
            "eventos": [{"id": "n1", "tipo_evento": "narracao", "texto": "Era uma vez."}],
        })  # não deve levantar

    def test_dialogue_still_requires_personagem(self):
        with self.assertRaises(SchemaError):
            validate_scene({
                "cena_id": "c", "ambientacao": "seco",
                "eventos": [{"id": "d1", "texto": "sem personagem"}],
            })

    def test_bad_tipo_evento_rejected(self):
        with self.assertRaises(SchemaError):
            validate_scene({
                "cena_id": "c", "ambientacao": "seco",
                "eventos": [{"id": "x", "tipo_evento": "musica_de_fundo",
                             "personagem": "Ana", "texto": "oi"}],
            })


if __name__ == "__main__":
    unittest.main()
