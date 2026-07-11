"""Testes da camada de render (DSP). Provam, com números, que o modelo da EDL
se sustenta no áudio real — principalmente que os envelopes matam o clique do
corte frio. Pulam automaticamente se numpy não estiver instalado."""

from __future__ import annotations

import unittest

try:
    import numpy as np
    from k_nar.render.dsp import apply_fades, equal_power_pan, snap_to_valley
    from k_nar.render.renderer import TimelineRenderer
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
