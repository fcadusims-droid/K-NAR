"""Testes do cache de síntese e da síntese em lote/paralela (resposta à latência)."""

from __future__ import annotations

import tempfile
import unittest

try:
    import numpy as np  # noqa: F401
    from k_nar.render.voice import FormantTTSBackend
    from k_nar.tts.batch import synthesize_all
    from k_nar.tts.cache import CachingTTS
    _HAS_NUMPY = True
except Exception:  # pragma: no cover
    _HAS_NUMPY = False

from k_nar.models import EntryDynamics, ExitDynamics, SpeechEvent, VoiceParams


def _ev(eid, text="uma fala de teste"):
    return SpeechEvent(id=eid, character="A", text=text, voice=VoiceParams(),
                       entry=EntryDynamics(), exit=ExitDynamics())


@unittest.skipUnless(_HAS_NUMPY, "numpy nao instalado")
class TestCache(unittest.TestCase):
    def test_hit_miss_e_persistencia(self):
        with tempfile.TemporaryDirectory() as d:
            c = CachingTTS(FormantTTSBackend(sr=24000), cache_dir=d)
            a = c.synthesize(_ev("x", "ola mundo"))
            self.assertEqual((c.hits, c.misses), (0, 1))
            b = c.synthesize(_ev("y", "ola mundo"))  # id diferente, MESMO conteudo
            self.assertEqual((c.hits, c.misses), (1, 1))  # cache por conteudo, nao por id
            self.assertTrue(np.array_equal(a.samples, b.samples))
            self.assertEqual(b.event_id, "y")  # mas devolve o id do chamador

    def test_texto_diferente_invalida(self):
        with tempfile.TemporaryDirectory() as d:
            c = CachingTTS(FormantTTSBackend(sr=24000), cache_dir=d)
            c.synthesize(_ev("x", "frase um"))
            c.synthesize(_ev("x", "frase dois"))
            self.assertEqual(c.misses, 2)  # conteudos distintos => dois misses

    def test_cache_sobrevive_a_nova_instancia(self):
        with tempfile.TemporaryDirectory() as d:
            CachingTTS(FormantTTSBackend(sr=24000), cache_dir=d).synthesize(_ev("x", "persistente"))
            c2 = CachingTTS(FormantTTSBackend(sr=24000), cache_dir=d)
            c2.synthesize(_ev("x", "persistente"))
            self.assertEqual((c2.hits, c2.misses), (1, 0))  # leu do disco


@unittest.skipUnless(_HAS_NUMPY, "numpy nao instalado")
class TestBatch(unittest.TestCase):
    def test_paralelo_bate_com_serial(self):
        backend = FormantTTSBackend(sr=24000)
        events = [_ev(f"e{i}", f"fala numero {i}") for i in range(5)]
        serial = {e.id: backend.synthesize(e) for e in events}
        parallel = synthesize_all(backend, events, workers=4)
        self.assertEqual(set(serial), set(parallel))
        for eid in serial:
            self.assertEqual(serial[eid].duration_ms, parallel[eid].duration_ms)


if __name__ == "__main__":
    unittest.main(verbosity=2)
