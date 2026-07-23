"""Nível 1 — o "set virtual" de zonas: SceneModel, SpacePolicy, integração. Stdlib+numpy."""

import unittest

from k_nar.models import Scene, SpeechEvent
from k_nar.narrative import RuleBasedScreenwriter
from k_nar.orchestrator import Orquestrador
from k_nar.space import SceneModel, SpacePolicy, Zone
from k_nar.tts.base import RenderedClip
from k_nar.tts.mock import MockTTSBackend

try:
    import numpy as np
    _HAS_NUMPY = True
except Exception:  # pragma: no cover
    _HAS_NUMPY = False


class TestSceneModel(unittest.TestCase):
    def _house(self):
        m = SceneModel()
        m.add_zone(Zone("cozinha", space="quarto_pequeno"))
        m.add_zone(Zone("sala", space="sala_grande"))
        m.add_zone(Zone("quintal", space="seco"))
        m.link("cozinha", "sala")            # porta cozinha<->sala
        m.default_zone = "cozinha"
        return m

    def test_hops_bfs(self):
        m = self._house()
        self.assertEqual(m.hops("cozinha", "cozinha"), 0)
        self.assertEqual(m.hops("cozinha", "sala"), 1)      # vizinhas
        self.assertEqual(m.hops("cozinha", "quintal"), -1)  # sem caminho

    def test_cue_same_zone_is_clean(self):
        m = self._house()
        m.move_listener("e", "sala"); m.place_source("e", "sala")
        cue = m.cue("e")
        self.assertTrue(cue.same_zone)
        self.assertEqual(cue.occlusion, 0.0)
        self.assertEqual(cue.space, "sala_grande")   # reverb do cômodo do ouvinte

    def test_cue_adjacent_is_occluded_and_far(self):
        m = self._house()
        m.move_listener("e", "cozinha"); m.place_source("e", "sala")
        cue = m.cue("e")
        self.assertFalse(cue.same_zone)
        self.assertGreater(cue.occlusion, 0.0)
        self.assertEqual(cue.distance, "longe")
        self.assertEqual(cue.space, "quarto_pequeno")  # reverb é do OUVINTE (cozinha)

    def test_cue_disconnected_is_more_occluded(self):
        m = self._house()
        m.move_listener("e", "cozinha"); m.place_source("e", "quintal")
        cue = m.cue("e")
        self.assertEqual(cue.distance, "muito_longe")
        self.assertGreater(cue.occlusion, 0.55)

    def test_trivial_when_one_zone(self):
        self.assertTrue(SceneModel(zones={"a": Zone("a")}).is_trivial())
        self.assertFalse(self._house().is_trivial())

    def test_roundtrip_serialization(self):
        m = self._house()
        m.move_listener("e", "cozinha"); m.place_source("e", "sala")
        m2 = SceneModel.from_dict(m.to_dict())
        self.assertEqual(m2.cue("e"), m.cue("e"))
        self.assertEqual(m2.default_zone, "cozinha")


class TestSpacePolicy(unittest.TestCase):
    def test_no_occlusion_is_transparent(self):
        lp, gain = SpacePolicy().resolve(0.0)
        self.assertEqual((lp, gain), (0.0, 0.0))

    def test_more_occlusion_darker_and_quieter(self):
        sp = SpacePolicy()
        lp_lo, g_lo = sp.resolve(0.4)
        lp_hi, g_hi = sp.resolve(0.9)
        self.assertGreater(lp_lo, lp_hi)   # mais oclusão -> corte mais BAIXO (mais escuro)
        self.assertLess(g_hi, g_lo)        # mais oclusão -> mais atenuação (dB menor)
        self.assertLess(g_hi, 0.0)


class TestScreenwriterZones(unittest.TestCase):
    def test_pov_walk_builds_zone_graph(self):
        prose = ("Herman entrou na cozinha e acendeu a luz. Depois foi para a sala. "
                 "Enfim saiu para o quintal e respirou fundo.")
        sc = RuleBasedScreenwriter().write(prose, lang="pt")
        esp = sc.get("espaco")
        self.assertIsNotNone(esp)
        zids = {z["id"] for z in esp["zonas"]}
        self.assertEqual(zids, {"cozinha", "sala", "quintal"})
        # o POV caminhou cozinha->sala->quintal: adjacências na ordem da caminhada
        links = {frozenset(p) for p in esp["ligacoes"]}
        self.assertIn(frozenset({"cozinha", "sala"}), links)
        self.assertIn(frozenset({"sala", "quintal"}), links)

    def test_single_room_emits_no_scene_model(self):
        sc = RuleBasedScreenwriter().write("Herman entrou na cozinha e sentou.", lang="pt")
        self.assertNotIn("espaco", sc)   # 1 cômodo: espacializar não muda nada

    def test_voice_from_another_room_is_occluded(self):
        # POV na sala; a voz vem "da cozinha" → fonte noutra zona (oclusão), POV não move
        prose = ('Herman estava na sala, lendo. Da cozinha, Baiano gritou: '
                 '"O jantar esta pronto!". Ele continuou na sala.')
        sc = RuleBasedScreenwriter().write(prose, lang="pt")
        esp = sc["espaco"]
        m = SceneModel.from_dict(esp)
        fala = next(e for e in esp["ouvinte"] if e.startswith("fala"))
        self.assertEqual(esp["ouvinte"][fala], "sala")      # ouvinte fica na sala
        self.assertEqual(esp["fontes"][fala], "cozinha")    # a voz vem da cozinha
        self.assertGreater(m.cue(fala).occlusion, 0.0)      # → abafada pela parede

    def test_narration_not_relocated_cross_room(self):
        # "um estrondo veio da cozinha" narrado: o NARRADOR não é movido p/ a cozinha
        prose = ("Herman estava na sala. Um barulho veio da cozinha. Ele ficou na sala.")
        sc = RuleBasedScreenwriter().write(prose, lang="pt")
        esp = sc.get("espaco", {})
        for eid, z in esp.get("ouvinte", {}).items():
            self.assertEqual(esp["fontes"].get(eid), z)   # nenhuma narração vira cross-room


class TestOrchestratorSpatial(unittest.TestCase):
    def _model(self):
        m = SceneModel()
        m.add_zone(Zone("sala", space="sala_grande"))
        m.add_zone(Zone("cozinha", space="sala_grande"))
        m.link("sala", "cozinha")
        m.default_zone = "sala"
        m.move_listener("perto", "sala"); m.place_source("perto", "sala")
        m.move_listener("longe", "sala"); m.place_source("longe", "cozinha")
        return m

    def _scene(self):
        return Scene(id="c", ambiance="seco", events=[
            SpeechEvent(id="perto", character="A", text="aqui"),
            SpeechEvent(id="longe", character="B", text="ali"),
        ])

    def _clips(self):
        return {"perto": RenderedClip("perto", 1000, samples=[0.0]),
                "longe": RenderedClip("longe", 1000, samples=[0.0])}

    def test_cross_room_voice_is_muffled_and_quieter(self):
        tl = Orquestrador(MockTTSBackend(), scene_model=self._model()).render_scene(
            self._scene(), clips=self._clips())
        perto = next(p for p in tl.placements if p.event_id == "perto")
        longe = next(p for p in tl.placements if p.event_id == "longe")
        self.assertEqual(perto.space, "sala_grande")
        self.assertGreater(longe.lowpass_hz, 0)     # oclusão abafa a voz do outro cômodo
        self.assertEqual(perto.lowpass_hz, 0)       # mesma zona: sem filtro
        self.assertLess(longe.gain_db, perto.gain_db)  # e mais baixa

    def test_trivial_model_is_noop(self):
        trivial = SceneModel()
        trivial.add_zone(Zone("so", space="sala_grande"))
        tl = Orquestrador(MockTTSBackend(), scene_model=trivial).render_scene(
            self._scene(), clips=self._clips())
        self.assertTrue(all(p.space == "" for p in tl.placements))  # não espacializa


@unittest.skipUnless(_HAS_NUMPY, "requer numpy")
class TestSpatialRender(unittest.TestCase):
    def _render(self, space, lowpass_hz=0.0):
        from k_nar.render.renderer import TimelineRenderer
        from k_nar.timeline import Placement, Timeline
        sr = 22050
        # 200ms de tom de 4kHz (agudo, p/ medir abafamento) — mono numpy
        t = np.arange(int(sr * 0.2)) / sr
        tone = (0.5 * np.sin(2 * np.pi * 4000 * t)).astype(np.float32)
        p = Placement(event_id="u", character="A", start_ms=0, duration_ms=200,
                      pan=0, text="", track="dialogo", space=space, lowpass_hz=lowpass_hz)
        tl = Timeline(scene_id="c", ambiance="seco", placements=[p], total_duration_ms=200)
        stereo = TimelineRenderer(sr=sr).render(tl, {"u": tone}, mode="full")
        return stereo, sr

    def test_space_adds_reverb_tail(self):
        dry, sr = self._render(space="")
        wet, _ = self._render(space="galpao_vazio")
        # o reverb do cômodo estende o sinal com uma cauda (ring-out) bem mais longa.
        self.assertGreater(wet.shape[1], dry.shape[1] + sr // 2)

    def test_occlusion_lowpass_kills_highs(self):
        # A oclusão da parede é um passa-baixa: mede a ENERGIA ABSOLUTA na banda aguda
        # (não a razão, nem pós-master, que normalizam) direto no primitivo do renderer.
        from k_nar.render import dsp
        sr = 22050
        t = np.arange(int(sr * 0.2)) / sr
        tone = (0.5 * np.sin(2 * np.pi * 4000 * t)).astype(np.float32)   # 4kHz puro
        muffled = dsp.lowpass_1pole(tone, 800.0, sr)                     # parede @800Hz

        def hf_energy(x):
            spec = np.abs(np.fft.rfft(x)) ** 2
            freqs = np.fft.rfftfreq(x.size, 1.0 / sr)
            return float(spec[freqs >= 3000].sum())

        self.assertLess(hf_energy(muffled), hf_energy(tone) * 0.25)  # agudo é comido


if __name__ == "__main__":
    unittest.main()
