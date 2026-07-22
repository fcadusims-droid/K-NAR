"""Integração: o Orquestrador ancora o corte de interrupção no forced alignment.

Sem numpy/piper. Monta uma cena de 2 falas (a 2ª interrompe a 1ª) e injeta clips
pré-sintetizados via `clips=`. Verifica que:
  * com alinhamento no clip anterior -> corte cai numa fronteira de fonema real,
    cut_method="fonema:*" e cut_snap_window_ms=0 (renderer aplica direto);
  * sem alinhamento -> fallback "energia", com a janela de tolerância na EDL.
"""

import unittest

from k_nar.align import Alignment, PhonemeSpan
from k_nar.models import (EntryDynamics, EntryType, Scene, SpeechEvent,
                          VoiceParams)
from k_nar.orchestrator import Orquestrador
from k_nar.timeline import TimingPolicy
from k_nar.tts.base import RenderedClip


class _NullTTS:
    """Nunca chamado: os clips vêm prontos via clips=."""

    def synthesize(self, event):  # pragma: no cover
        raise AssertionError("não deveria sintetizar")


def _scene():
    a = SpeechEvent(id="a", character="A", text="fala longa que sera cortada",
                    voice=VoiceParams(tension=0.5))
    b = SpeechEvent(id="b", character="B", text="interrompe",
                    voice=VoiceParams(tension=0.8),
                    entry=EntryDynamics(type=EntryType.INTERRUPTION, aggressiveness=0.3))
    return Scene(id="c", ambiance="seco", events=[a, b])


class TestForcedAlignmentCut(unittest.TestCase):
    def test_cut_snaps_to_word_boundary(self):
        sr = 1000
        # clip "a": 2000ms. Fronteira de palavra em 1400 (amostra 1400).
        align_a = Alignment([
            PhonemeSpan("x", 0, 1350),
            PhonemeSpan(" ", 1350, 1400),   # fronteira de palavra
            PhonemeSpan("y", 1400, 2000),
        ], sample_rate=sr)
        clips = {
            "a": RenderedClip("a", duration_ms=2000, sample_rate=sr,
                              samples=[0.0], alignment=align_a),
            "b": RenderedClip("b", duration_ms=800, sample_rate=sr, samples=[0.0]),
        }
        tl = Orquestrador(_NullTTS(), TimingPolicy()).render_scene(_scene(), clips=clips)
        prev = next(p for p in tl.placements if p.event_id == "a")

        # agressividade 0.3 => entra ~1400ms. A fronteira de palavra fica no INÍCIO
        # do span de espaço (1350 = fim exato da palavra "x", antes do silêncio),
        # que tem peso maior que o início de "y" (1400, só fonema).
        self.assertTrue(prev.cut_method.startswith("fonema:palavra"))
        # o Orquestrador ancora na fronteira e deixa o renderer refinar numa janela
        # ESTREITA (não a larga do fallback de energia).
        self.assertEqual(prev.cut_snap_window_ms, TimingPolicy().cut_refine_window_ms)
        self.assertLess(prev.cut_snap_window_ms, TimingPolicy().cut_snap_window_ms)
        self.assertIsNotNone(prev.hard_cut_ms)
        # corta no fim da palavra (1350ms), não no alvo cru nem no meio de "y"
        self.assertEqual(prev.hard_cut_ms, 1350)

    def test_fallback_energy_without_alignment(self):
        sr = 1000
        clips = {
            "a": RenderedClip("a", duration_ms=2000, sample_rate=sr, samples=[0.0]),
            "b": RenderedClip("b", duration_ms=800, sample_rate=sr, samples=[0.0]),
        }
        policy = TimingPolicy()
        tl = Orquestrador(_NullTTS(), policy).render_scene(_scene(), clips=clips)
        prev = next(p for p in tl.placements if p.event_id == "a")

        self.assertEqual(prev.cut_method, "energia")
        self.assertEqual(prev.cut_snap_window_ms, policy.cut_snap_window_ms)
        self.assertIsNotNone(prev.hard_cut_ms)

    def test_floor_prevents_cutting_too_early(self):
        sr = 1000
        # única fronteira de palavra está MUITO cedo (200ms); o piso min_audible
        # deve impedir o corte lá e manter o alvo/fronteira mais tardia.
        align_a = Alignment([
            PhonemeSpan("x", 0, 150),
            PhonemeSpan(" ", 150, 200),     # cedo demais (abaixo do piso de 400ms)
            PhonemeSpan("y", 200, 2000),
        ], sample_rate=sr)
        clips = {
            "a": RenderedClip("a", duration_ms=2000, sample_rate=sr,
                              samples=[0.0], alignment=align_a),
            "b": RenderedClip("b", duration_ms=800, sample_rate=sr, samples=[0.0]),
        }
        tl = Orquestrador(_NullTTS(), TimingPolicy()).render_scene(_scene(), clips=clips)
        prev = next(p for p in tl.placements if p.event_id == "a")
        # a fronteira em 200 está abaixo do piso (min_audible_ms=400) => não usada
        self.assertGreaterEqual(prev.hard_cut_ms, 400)


if __name__ == "__main__":
    unittest.main()
