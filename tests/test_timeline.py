"""Testes da lógica das duas passagens — rodam offline, só com o mock.

Provam a tese central da arquitetura: a MESMA agressividade relativa produz
cortes em ms diferentes conforme a duração real da fala anterior.
"""

from __future__ import annotations

import unittest

from k_nar import (
    DramaticPause,
    EntryDynamics,
    EntryType,
    ExitDynamics,
    MockTTSBackend,
    Orquestrador,
    Scene,
    SpeechEvent,
    TimingPolicy,
    VoiceParams,
)
from k_nar.tts.base import RenderedClip


class FixedTTS:
    """TTS de teste: duração fixa por evento (independe do texto)."""

    def __init__(self, durations: dict[str, int]):
        self.durations = durations

    def synthesize(self, event: SpeechEvent) -> RenderedClip:
        return RenderedClip(event_id=event.id, duration_ms=self.durations[event.id])


def _ev(eid, entry_type=EntryType.SEQUENTIAL, agg=0.0, pause=DramaticPause.NONE):
    return SpeechEvent(
        id=eid,
        character=eid,
        text="x",
        voice=VoiceParams(),
        entry=EntryDynamics(type=entry_type, aggressiveness=agg),
        exit=ExitDynamics(dramatic_pause=pause),
    )


class TestSequential(unittest.TestCase):
    def test_sequential_respeita_pausa(self):
        scene = Scene(
            id="s",
            ambiance="seco",
            events=[
                _ev("a", pause=DramaticPause.SHORT),  # 200ms de pausa
                _ev("b"),
            ],
        )
        tts = FixedTTS({"a": 1000, "b": 800})
        tl = Orquestrador(tts, TimingPolicy()).render_scene(scene)
        a, b = tl.placements
        self.assertEqual(a.start_ms, 0)
        self.assertEqual(a.natural_end_ms, 1000)
        # b começa depois de a (1000) + pausa curta (200) = 1200
        self.assertEqual(b.start_ms, 1200)
        self.assertIsNone(a.hard_cut_ms)


class TestInterruption(unittest.TestCase):
    def test_agressividade_relativa_escala_com_duracao(self):
        """Mesma agressividade (0.25), durações diferentes -> cortes diferentes."""
        policy = TimingPolicy()

        # anterior curto: 2000ms
        s1 = Scene("s", "seco", [_ev("a"), _ev("b", EntryType.INTERRUPTION, agg=0.25)])
        tl1 = Orquestrador(FixedTTS({"a": 2000, "b": 500}), policy).render_scene(s1)
        # anterior longo: 4000ms
        s2 = Scene("s", "seco", [_ev("a"), _ev("b", EntryType.INTERRUPTION, agg=0.25)])
        tl2 = Orquestrador(FixedTTS({"a": 4000, "b": 500}), policy).render_scene(s2)

        start_curto = tl1.placements[1].start_ms
        start_longo = tl2.placements[1].start_ms
        # 0.25 => entra em 75% do anterior
        self.assertEqual(start_curto, 1500)  # 75% de 2000
        self.assertEqual(start_longo, 3000)  # 75% de 4000
        self.assertNotEqual(start_curto, start_longo)  # a tese, provada

    def test_interrupcao_corta_a_fala_anterior(self):
        s = Scene("s", "seco", [_ev("a"), _ev("b", EntryType.INTERRUPTION, agg=0.3)])
        tl = Orquestrador(FixedTTS({"a": 3000, "b": 500}), TimingPolicy()).render_scene(s)
        a, b = tl.placements
        self.assertEqual(a.hard_cut_ms, b.start_ms)   # a foi cortada onde b entra
        self.assertEqual(a.end_ms, b.start_ms)        # fim efetivo respeita o corte

    def test_guarda_de_inteligibilidade(self):
        """Agressividade absurda não engole a fala inteira do anterior."""
        policy = TimingPolicy(min_audible_ms=400, min_audible_fraction=0.35)
        s = Scene("s", "seco", [_ev("a"), _ev("b", EntryType.INTERRUPTION, agg=1.0)])
        tl = Orquestrador(FixedTTS({"a": 1000, "b": 500}), policy).render_scene(s)
        a, b = tl.placements
        # 35% de 1000 = 350, mas o piso absoluto é 400 -> vence 400
        self.assertEqual(b.start_ms, 400)
        self.assertGreater(a.end_ms, 0)


class TestOverlapAndQA(unittest.TestCase):
    def test_overlap_nao_corta(self):
        s = Scene("s", "seco", [_ev("a"), _ev("b", EntryType.OVERLAP, agg=0.4)])
        tl = Orquestrador(FixedTTS({"a": 2000, "b": 1000}), TimingPolicy()).render_scene(s)
        a, _ = tl.placements
        self.assertIsNone(a.hard_cut_ms)  # sobreposição não corta ninguém

    def test_qa_detecta_sobreposicao(self):
        s = Scene("s", "seco", [_ev("a"), _ev("b", EntryType.INTERRUPTION, agg=0.3)])
        tl = Orquestrador(FixedTTS({"a": 3000, "b": 500}), TimingPolicy()).render_scene(s)
        overlaps = tl.overlaps()
        self.assertEqual(len(overlaps), 1)
        self.assertEqual(overlaps[0][0], "a")
        self.assertEqual(overlaps[0][1], "b")


class TestMockDeterminismo(unittest.TestCase):
    def test_mock_e_deterministico(self):
        ev = _ev("a")
        ev.text = "uma frase de teste com seis palavras"
        m = MockTTSBackend()
        self.assertEqual(m.synthesize(ev).duration_ms, m.synthesize(ev).duration_ms)


if __name__ == "__main__":
    unittest.main(verbosity=2)
