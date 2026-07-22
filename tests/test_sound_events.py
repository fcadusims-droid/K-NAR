"""Fase 5 — eventos de som (SFX/ambiência) no modelo, orquestrador e schema. Stdlib."""

import unittest

from k_nar.models import (AmbienceEvent, Scene, SfxEvent, SpeechEvent, Track,
                          build_event)
from k_nar.orchestrator import Orquestrador
from k_nar.schema import SchemaError, validate_scene
from k_nar.tts.base import RenderedClip
from k_nar.tts.mock import MockTTSBackend


class TestSoundModels(unittest.TestCase):
    def test_build_event_sfx(self):
        ev = build_event({"id": "s1", "tipo_evento": "sfx", "tag": "tiro"})
        self.assertIsInstance(ev, SfxEvent)
        self.assertEqual(ev.track, Track.SFX)
        self.assertEqual(ev.tag, "tiro")

    def test_build_event_ambience(self):
        ev = build_event({"id": "a1", "tipo_evento": "ambiencia", "tag": "chuva"})
        self.assertIsInstance(ev, AmbienceEvent)
        self.assertEqual(ev.track, Track.AMBIENCE)

    def test_sfx_reads_gatilho_alias(self):
        ev = SfxEvent.from_dict({"id": "s", "gatilho": "explosao"})
        self.assertEqual(ev.tag, "explosao")


class TestSoundOrchestration(unittest.TestCase):
    def _scene(self):
        return Scene(id="c", ambiance="seco", events=[
            AmbienceEvent(id="amb", tag="motor", gain_db=-18),
            SpeechEvent(id="d1", character="A", text="fala um"),
            SfxEvent(id="sfx", tag="tiro", gain_db=-2),
            SpeechEvent(id="d2", character="B", text="reage ao tiro"),
        ])

    def _clips(self):
        # clips prontos (o Orquestrador não sintetiza som): duração fixa, sem numpy
        return {
            "amb": RenderedClip("amb", 3000, samples=[0.0]),
            "d1": RenderedClip("d1", 1000, samples=[0.0]),
            "sfx": RenderedClip("sfx", 500, samples=[0.0]),
            "d2": RenderedClip("d2", 1200, samples=[0.0]),
        }

    def test_tracks_assigned(self):
        tl = Orquestrador(MockTTSBackend()).render_scene(self._scene(), clips=self._clips())
        tracks = {p.event_id: p.track for p in tl.placements}
        self.assertEqual(tracks["d1"], "dialogo")
        self.assertEqual(tracks["sfx"], "sfx")
        self.assertEqual(tracks["amb"], "ambiencia")

    def test_sfx_is_sequenced_between_speech(self):
        # d1 -> tiro -> d2 (reação): o SFX ocupa o tempo entre as falas
        tl = Orquestrador(MockTTSBackend()).render_scene(self._scene(), clips=self._clips())
        d1 = next(p for p in tl.placements if p.event_id == "d1")
        sfx = next(p for p in tl.placements if p.event_id == "sfx")
        d2 = next(p for p in tl.placements if p.event_id == "d2")
        self.assertGreaterEqual(sfx.start_ms, d1.natural_end_ms)
        self.assertGreaterEqual(d2.start_ms, sfx.natural_end_ms)

    def test_ambience_spans_whole_scene(self):
        tl = Orquestrador(MockTTSBackend()).render_scene(self._scene(), clips=self._clips())
        amb = next(p for p in tl.placements if p.event_id == "amb")
        self.assertEqual(amb.start_ms, 0)
        self.assertEqual(amb.end_ms, tl.total_duration_ms)

    def test_sfx_gain_is_own_not_tension(self):
        tl = Orquestrador(MockTTSBackend()).render_scene(self._scene(), clips=self._clips())
        sfx = next(p for p in tl.placements if p.event_id == "sfx")
        self.assertEqual(sfx.gain_db, -2.0)

    def test_missing_sfx_clip_skipped_gracefully(self):
        clips = self._clips()
        del clips["sfx"]   # SFX não renderizado
        tl = Orquestrador(MockTTSBackend()).render_scene(self._scene(), clips=clips)
        self.assertNotIn("sfx", {p.event_id for p in tl.placements})


class TestSoundSchema(unittest.TestCase):
    def test_sfx_event_needs_tag_not_texto(self):
        validate_scene({
            "cena_id": "c", "ambientacao": "seco",
            "eventos": [{"id": "s1", "tipo_evento": "sfx", "tag": "tiro"}],
        })  # não deve levantar

    def test_sfx_without_tag_rejected(self):
        with self.assertRaises(SchemaError):
            validate_scene({
                "cena_id": "c", "ambientacao": "seco",
                "eventos": [{"id": "s1", "tipo_evento": "sfx"}],
            })

    def test_mixed_scene_validates(self):
        validate_scene({
            "cena_id": "c", "ambientacao": "seco",
            "eventos": [
                {"id": "a1", "tipo_evento": "ambiencia", "tag": "floresta_noite"},
                {"id": "d1", "personagem": "Ana", "texto": "oi"},
                {"id": "s1", "tipo_evento": "sfx", "tag": "trovao"},
            ],
        })


if __name__ == "__main__":
    unittest.main()
