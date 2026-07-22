"""Testes do Screenwriter (PASSAGEM 0) e da cadeia prosa→Director→cena. Stdlib puro."""

import unittest

from k_nar.director import RuleBasedDirector
from k_nar.models import NarrationEvent, Scene, SpeechEvent
from k_nar.narrative import RuleBasedScreenwriter
from k_nar.schema import validate_scene


def _write(prose):
    return RuleBasedScreenwriter().write(prose, scene_id="c", ambiance="seco")


class TestSegmentation(unittest.TestCase):
    def test_narration_vs_dialogue(self):
        out = _write('A porta abriu. "Ola?", disse Ana.')
        tipos = [(e["tipo"], e["texto"]) for e in out["elementos"]]
        self.assertEqual(tipos[0], ("narracao", "A porta abriu."))
        self.assertEqual(tipos[1][0], "fala")
        self.assertEqual(tipos[1][1], "Ola?")

    def test_speaker_from_attribution(self):
        out = _write('"Fujam!", gritou o Capitao.')
        fala = out["elementos"][0]
        self.assertEqual(fala["personagem"], "Capitao")
        self.assertEqual(fala["deixa"], "gritou")

    def test_speaker_carries_over_when_absent(self):
        out = _write('"Primeiro", disse Bruno. "Segundo tambem."')
        falas = [e for e in out["elementos"] if e["tipo"] == "fala"]
        self.assertEqual(falas[0]["personagem"], "Bruno")
        self.assertEqual(falas[1]["personagem"], "Bruno")  # herda o ultimo locutor

    def test_narration_after_quote_not_swallowed(self):
        # a fala termina com '.' dentro das aspas; a narracao seguinte deve sobreviver
        out = _write('Ela sussurrou: "Estou aqui." Uma luz se acendeu.')
        textos = [e["texto"] for e in out["elementos"]]
        self.assertIn("Uma luz se acendeu.", textos)

    def test_action_triggers_collected(self):
        out = _write("A porta rangeu. Um trovao ecoou.")
        gatilhos = {a["gatilho"] for a in out["acoes"]}
        self.assertIn("porta_range", gatilhos)
        self.assertIn("trovao", gatilhos)

    def test_dialogue_with_internal_punctuation(self):
        # ponto/interrogacao dentro das aspas nao corta a fala no meio
        out = _write('"Voce vem? Ou nao?", perguntou ele.')
        falas = [e for e in out["elementos"] if e["tipo"] == "fala"]
        self.assertEqual(len(falas), 1)
        self.assertEqual(falas[0]["texto"], "Voce vem? Ou nao?")


class TestScreenwriterToDirectorToScene(unittest.TestCase):
    def test_full_chain_produces_valid_scene(self):
        # prosa sem gatilhos de som (foco em narração + diálogo)
        prose = ('O quarto estava escuro. "Segurem-se!", gritou a Comandante. '
                 'Ela fechou os olhos com forca.')
        script = _write(prose)
        scene_dict = RuleBasedDirector().direct(script)
        validate_scene(scene_dict)  # portão estrito
        scene = Scene.from_dict(scene_dict)

        kinds = [type(e).__name__ for e in scene.events]
        self.assertEqual(kinds, ["NarrationEvent", "SpeechEvent", "NarrationEvent"])

    def test_loud_cue_raises_tension(self):
        # a mesma fala neutra, mas com deixa "gritou", deve subir a tensao
        neutra = RuleBasedDirector().direct(_write('Ana falou: "tudo bem entao".'))
        gritada = RuleBasedDirector().direct(_write('Ana gritou: "tudo bem entao".'))
        t_neutra = neutra["eventos"][0]["voz"]["tensao"]
        t_gritada = gritada["eventos"][0]["voz"]["tensao"]
        ordem = {"baixa": 0, "media": 1, "alta": 2, "extrema": 3}
        self.assertGreater(ordem[t_gritada], ordem[t_neutra])

    def test_narration_events_are_sequential(self):
        script = _write("O tempo passava devagar. A tarde caia sobre o vale.")
        scene = RuleBasedDirector().direct(script)
        narracoes = [e for e in scene["eventos"] if e.get("tipo_evento") == "narracao"]
        self.assertTrue(narracoes)
        for ev in narracoes:
            self.assertEqual(ev["entrada"]["tipo"], "sequencial")

    def test_sound_cue_becomes_sfx_not_narration(self):
        # a IDEIA central: "passos numa poca" vira SOM, o narrador NÃO lê
        out = _write("Passos numa poca d'agua.")
        tipos = [e["tipo"] for e in out["elementos"]]
        self.assertIn("sfx", tipos)
        self.assertNotIn("narracao", tipos)
        sfx = next(e for e in out["elementos"] if e["tipo"] == "sfx")
        self.assertEqual(sfx["tag"], "passos_poca")

    def test_ambience_bed_detected(self):
        out = _write("A floresta noturna se estendia ao redor.")
        amb = [e for e in out["elementos"] if e["tipo"] == "ambiencia"]
        self.assertEqual(len(amb), 1)
        self.assertEqual(amb[0]["tag"], "floresta_noite")

    def test_ambience_deduped(self):
        out = _write("Chovia forte. A chuva batia no vidro. Chovia sem parar.")
        amb = [e for e in out["elementos"] if e["tipo"] == "ambiencia"]
        self.assertEqual(len(amb), 1)  # uma cama de chuva, não três

    def test_narrator_optional_radiodrama(self):
        prose = 'A floresta escura. "Corram!", gritou o guia. Um tiro soou.'
        com = RuleBasedScreenwriter().write(prose, narrator=True)
        sem = RuleBasedScreenwriter().write(prose, narrator=False)
        self.assertTrue(any(e["tipo"] == "narracao" for e in com["elementos"]))
        self.assertFalse(any(e["tipo"] == "narracao" for e in sem["elementos"]))
        # diálogo e som permanecem mesmo sem narrador
        self.assertTrue(any(e["tipo"] == "fala" for e in sem["elementos"]))
        self.assertTrue(any(e["tipo"] in ("sfx", "ambiencia") for e in sem["elementos"]))

    def test_narrated_sentence_with_name_still_narrated(self):
        # frase com nome próprio + som não é "som puro": narra E emite o SFX
        out = _write("Ana ouviu a porta que rangeu ao fundo do corredor.")
        tipos = [e["tipo"] for e in out["elementos"]]
        self.assertIn("narracao", tipos)
        self.assertIn("sfx", tipos)

    def test_action_cues_passed_to_scene(self):
        script = _write("A porta rangeu bem devagar.")
        scene = RuleBasedDirector().direct(script)
        self.assertTrue(scene.get("acoes"))
        self.assertEqual(scene["acoes"][0]["gatilho"], "porta_range")


if __name__ == "__main__":
    unittest.main()
