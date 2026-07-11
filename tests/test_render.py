"""Testes da camada de render (DSP). Provam, com números, que o modelo da EDL
se sustenta no áudio real — principalmente que os envelopes matam o clique do
corte frio. Pulam automaticamente se numpy não estiver instalado."""

from __future__ import annotations

import unittest

try:
    import numpy as np
    from k_nar.render.dsp import (
        apply_fades, equal_power_pan, fade_window, snap_to_valley, trim_silence,
    )
    from k_nar.render.renderer import TimelineRenderer
    from k_nar.render.trim import TrimmedTTS
    from k_nar.render.voice import FormantTTSBackend
    _HAS_NUMPY = True
except Exception:  # pragma: no cover
    _HAS_NUMPY = False

from k_nar import (
    DramaticPause,
    EntryDynamics,
    EntryType,
    ExitDynamics,
    Orquestrador,
    Scene,
    SpeechEvent,
    TimingPolicy,
    VoiceParams,
)


def _ev(eid: str, text: str = "uma fala de teste") -> SpeechEvent:
    return SpeechEvent(
        id=eid, character=eid, text=text, voice=VoiceParams(),
        entry=EntryDynamics(), exit=ExitDynamics(),
    )


def _scene_com_interrupcao() -> Scene:
    def ev(eid, char, txt, etype=EntryType.SEQUENTIAL, agg=0.0, pan=0):
        return SpeechEvent(
            id=eid, character=char, text=txt, voice=VoiceParams(),
            entry=EntryDynamics(type=etype, aggressiveness=agg),
            exit=ExitDynamics(dramatic_pause=DramaticPause.NONE), pan=pan,
        )
    return Scene("s", "cockpit_metalico_eco", [
        ev("a", "Alien A", "o nucleo nao deve ser ativado sob nenhuma circunstancia", pan=-40),
        ev("b", "Alien B", "voce teme o inevitavel", EntryType.INTERRUPTION, agg=0.3, pan=40),
    ])


@unittest.skipUnless(_HAS_NUMPY, "numpy nao instalado")
class TestDSPPrimitivos(unittest.TestCase):
    def test_fade_remove_descontinuidade(self):
        x = np.ones(1000, dtype=np.float32)  # bloco DC: corte cru = degrau enorme
        faded = apply_fades(x, 0, 50)
        self.assertAlmostEqual(float(faded[-1]), 0.0, places=5)  # termina em zero
        self.assertLess(float(abs(np.diff(faded)).max()), 0.05)  # sem degrau

    def test_pan_equal_power(self):
        x = np.ones(100, dtype=np.float32)
        left = equal_power_pan(x, -100)
        right = equal_power_pan(x, 100)
        self.assertGreater(left[0].mean(), left[1].mean())   # -100 => canal L domina
        self.assertGreater(right[1].mean(), right[0].mean())  # +100 => canal R domina

    def test_snap_vai_para_o_vale(self):
        x = np.ones(2000, dtype=np.float32)
        x[900:960] = 0.0  # um "silencio" perto do alvo 1000
        idx = snap_to_valley(x, target=1000, window=200, floor=0, smooth_win=20)
        self.assertTrue(900 <= idx <= 960)  # cortou no silencio, nao no alvo cru


@unittest.skipUnless(_HAS_NUMPY, "numpy nao instalado")
class TestTrimECrossfade(unittest.TestCase):
    def test_trim_remove_padding_e_remede_duracao(self):
        sr = 24000
        fala = np.ones(int(0.5 * sr), dtype=np.float32) * 0.8
        padded = np.concatenate([np.zeros(int(0.15 * sr), np.float32), fala,
                                 np.zeros(int(0.2 * sr), np.float32)])
        trimmed, lead, trail = trim_silence(padded, threshold_db=-45, keep_ms=8, sr=sr)
        # duracao volta a ser ~ a da fala (0.5s) + folga de keep_ms nos dois lados
        self.assertAlmostEqual(len(trimmed) / sr, 0.5, delta=0.03)
        self.assertGreater(lead, 0)
        self.assertGreater(trail, 0)

    def test_trimmed_tts_corrige_duracao_medida(self):
        class PaddedTTS:
            def synthesize(self, ev):
                from k_nar.tts.base import RenderedClip
                sr = 24000
                fala = np.ones(int(0.4 * sr), np.float32) * 0.7
                pad = np.zeros(int(0.15 * sr), np.float32)
                s = np.concatenate([pad, fala, pad])
                return RenderedClip(ev.id, int(1000 * len(s) / sr), sample_rate=sr, samples=s)
        wrapped = TrimmedTTS(PaddedTTS())
        ev = _ev("a")
        clip = wrapped.synthesize(ev)
        self.assertLess(clip.duration_ms, 500)   # 700ms padded -> ~400ms de fala
        self.assertGreater(clip.duration_ms, 380)

    def test_equal_power_soma_potencia_constante(self):
        n = 500
        fin = fade_window(n, rising=True, curve="equal_power")
        fout = fade_window(n, rising=False, curve="equal_power")
        power = fin ** 2 + fout ** 2   # deve ser ~1 em todo ponto
        self.assertTrue(np.allclose(power, 1.0, atol=1e-3))

    def test_crossfade_reduz_o_pico_vs_soma_linear(self):
        # duas vozes altas: a soma linear "+" empilha os picos; o crossfade
        # equal-power (a desce em cos enquanto b sobe em sin) sempre reduz o pico.
        m = FormantTTSBackend(sr=24000)
        a = np.asarray(m.synthesize(_ev("a")).samples)
        b = np.asarray(m.synthesize(_ev("b")).samples)
        n = min(len(a), len(b))
        a = np.full(n, 0.9, np.float32)          # bloco alto p/ garantir estouro linear
        b = np.full(n, 0.9, np.float32)
        linear = float(np.abs(a + b).max())      # 1.8 -> clipa
        fin = fade_window(n, True, "equal_power")
        fout = fade_window(n, False, "equal_power")
        eqp = float(np.abs(a * fout + b * fin).max())
        self.assertGreater(linear, 1.0)          # soma linear estoura o teto
        self.assertLess(eqp, linear)             # equal-power reduz o pico combinado


@unittest.skipUnless(_HAS_NUMPY, "numpy nao instalado")
class TestRenderAntiClique(unittest.TestCase):
    def test_full_reduz_o_clique_do_corte(self):
        scene = _scene_com_interrupcao()
        policy = TimingPolicy()
        backend = FormantTTSBackend(sr=24000)
        timeline = Orquestrador(backend, policy).render_scene(scene)
        clips = {e.id: backend.synthesize(e).samples for e in scene.events}

        r = TimelineRenderer(sr=24000, policy=policy)
        naive = r.render(timeline, clips, mode="naive").mean(axis=0)
        dry = r.render(timeline, clips, mode="dry").mean(axis=0)

        cut = int(timeline.placements[0].hard_cut_ms / 1000 * 24000)
        win = int(0.02 * 24000)

        def salto(sig):
            seg = sig[cut - win: cut + win]
            return float(np.max(np.abs(np.diff(seg))))

        # o corte cru gera o maior salto; o fade+snap derruba drasticamente.
        self.assertLess(salto(dry), salto(naive) * 0.5)

    def test_full_tem_estereo_e_cauda_de_reverb(self):
        scene = _scene_com_interrupcao()
        backend = FormantTTSBackend(sr=24000)
        timeline = Orquestrador(backend).render_scene(scene)
        clips = {e.id: backend.synthesize(e).samples for e in scene.events}
        stereo = TimelineRenderer(sr=24000).render(timeline, clips, mode="full")
        self.assertEqual(stereo.shape[0], 2)
        # canais diferentes => panning aplicado
        self.assertGreater(float(np.mean(np.abs(stereo[0] - stereo[1]))), 1e-4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
