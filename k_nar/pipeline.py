"""Pipeline de alto nível: `Story` → áudio. O que a CLI e a GitHub Action chamam.

Junta as passagens numa função só (`render_story`), escolhendo voz por idioma e som
por biblioteca/síntese. Fica FORA do core (`k_nar/__init__`) porque toca no render
(numpy/pedalboard); os imports pesados são tardios.

    from k_nar.story import load_story
    from k_nar.pipeline import render_story
    res = render_story(load_story("historia.md"))
    res.write("out.wav")
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from k_nar.lang import get_language
from k_nar.story import Story

_SOUND_TRACKS = {"sfx", "ambiencia"}


@dataclass
class RenderResult:
    stereo: object          # np.ndarray (2, N)
    sr: int
    timeline: object        # Timeline
    issues: list            # list[QAIssue]
    voice_kind: str         # "piper" | "formante"
    script: dict            # roteiro estruturado do Screenwriter (elementos/acoes)
    scene: object           # Scene montada pelo Director
    person: str = "terceira"  # pessoa narrativa resolvida ("primeira" | "terceira")

    def write(self, path: str) -> str:
        from k_nar.render.renderer import TimelineRenderer
        TimelineRenderer(sr=self.sr).write_wav(str(path), self.stereo)
        return str(path)


def _voice_backend(lang_profile, prosody, models_dir: str,
                   profiles: dict | None = None):
    """Piper (por idioma) se os modelos existirem; senão, formante sintético.

    `profiles` já traz o elenco (voz por personagem, do casting) + o narrador. No
    fallback formante, injetamos o pitch de cada perfil na prosódia compartilhada p/
    as vozes ainda saírem distintas."""
    profiles = profiles or {}
    main = Path(models_dir) / lang_profile.main_voice
    if main.exists():
        from k_nar.render.trim import TrimmedTTS
        from k_nar.tts.cache import CachingTTS
        from k_nar.tts.multivoice import MultiVoiceTTSBackend
        mv = MultiVoiceTTSBackend(default_model=str(main), profiles=profiles, prosody=prosody)
        return CachingTTS(TrimmedTTS(mv), cache_dir=".knar_cache"), 22050, "piper"
    # formante: sem roteamento de modelo, mas o pitch por personagem ainda diferencia.
    for ch, prof in profiles.items():
        if prof.pitch_shift:
            prosody.character_pitch[ch] = prosody.character_pitch.get(ch, 0.0) + prof.pitch_shift
    from k_nar.render.voice import FormantTTSBackend
    return FormantTTSBackend(sr=24000), 24000, "formante"


def _build_profiles(scene, story, lang_profile, models_dir: str):
    """Monta os VoiceProfile: elenco (voz por aparência/idade/gênero) + narrador.

    A PESSOA decide o narrador: em 3ª pessoa, voz onisciente própria (modelo do
    narrador). Em 1ª pessoa, a narração É o protagonista — usa a MESMA voz dele (se
    nomeado) ou a voz base do idioma (íntima, distinta do narrador de 3ª pessoa).
    Devolve (profiles, person, protagonista_efetivo)."""
    from k_nar.casting import cast_voices
    from k_nar.narrative import detect_person, resolve_person
    from k_nar.tts.multivoice import VoiceProfile

    def _track(ev):
        return getattr(getattr(ev, "track", None), "value", "dialogo")

    speakers = [ev.character for ev in scene.events
                if _track(ev) == "dialogo" and getattr(ev, "character", "")]
    profiles = cast_voices(sorted(set(speakers)), story.prose, story.lang)

    # pessoa: front-matter manda; "auto" detecta pela narração.
    narration = " ".join(getattr(ev, "text", "") for ev in scene.events
                         if _track(ev) == "narracao")
    person = resolve_person(story.person)
    if person == "auto":
        person = detect_person(narration, story.lang)

    narr_model = Path(models_dir) / lang_profile.narrator_voice
    main_model = Path(models_dir) / lang_profile.main_voice
    protagonist = story.protagonist.strip()
    if person == "primeira":
        if protagonist and protagonist in profiles:
            profiles["Narrador"] = profiles[protagonist]      # narração = voz do protagonista
        else:
            # voz de 1ª pessoa: modelo base, neutra e próxima (≠ narrador onisciente).
            profiles["Narrador"] = VoiceProfile(model_path=str(main_model))
    else:
        profiles["Narrador"] = VoiceProfile(
            model_path=str(narr_model if narr_model.exists() else main_model))
    return profiles, person, protagonist


def _sfx_backend(sr: int, sounds_dir: str | None):
    """Biblioteca de samples reais se houver manifesto; senão, síntese procedural."""
    from k_nar.sfx import ProceduralSfxBackend
    procedural = ProceduralSfxBackend(sr=sr)
    if sounds_dir:
        manifest = Path(sounds_dir) / "manifest.json"
        if manifest.exists():
            import json
            from k_nar.sfx import LibrarySfxBackend
            data = json.loads(manifest.read_text("utf-8"))
            return LibrarySfxBackend(data, sr=sr, base_dir=sounds_dir, fallback=procedural)
    return procedural


def render_story(story: Story, *, models_dir: str = "models/piper",
                 sounds_dir: str | None = None, mode: str = "full",
                 spatialize: bool = True) -> RenderResult:
    """Roda a cadeia completa Screenwriter → Director → Orquestrador → Renderer.

    `spatialize`: liga o "set virtual" de zonas (Nível 1) quando o Screenwriter detecta
    >=2 cômodos — o reverb segue o POV pela casa e vozes de outros cômodos soam
    abafadas (oclusão). Sem >=2 cômodos, é no-op (idêntico ao modo clássico)."""
    from k_nar import (Orquestrador, ProsodyPolicy, Scene, TimingPolicy, check_mix,
                       check_timeline)
    from k_nar.director import RuleBasedDirector
    from k_nar.narrative import RuleBasedScreenwriter
    from k_nar.render import dsp
    from k_nar.render.renderer import TimelineRenderer
    from k_nar.space import SceneModel

    lang_profile = get_language(story.lang)

    # PASSAGEM 0 → 1
    script = RuleBasedScreenwriter().write(
        story.prose, scene_id=story.scene_id, ambiance=story.ambiance,
        narrator=story.narrator, lang=story.lang)
    scene_dict = RuleBasedDirector().direct(script)
    scene = Scene.from_dict(scene_dict)

    # "Set virtual" de zonas (Nível 1): reconstruído do roteiro se o Screenwriter achou
    # cômodos e `spatialize` está ligado. Trivial (0/1 zona) → o Orquestrador ignora.
    scene_model = None
    if spatialize and script.get("espaco"):
        scene_model = SceneModel.from_dict(script["espaco"])

    # Elenco de vozes (aparência/idade/gênero) + narrador, e a PESSOA narrativa.
    profiles, person, _protagonist = _build_profiles(scene, story, lang_profile, models_dir)

    # PASSAGENS 2-3
    prosody = ProsodyPolicy()
    policy = TimingPolicy()
    voice, sr, kind = _voice_backend(lang_profile, prosody, models_dir, profiles)
    sfxb = _sfx_backend(sr, sounds_dir)

    def _track(ev):
        return getattr(getattr(ev, "track", None), "value", "dialogo")

    speech = [ev for ev in scene.events if _track(ev) not in _SOUND_TRACKS]
    sound = [ev for ev in scene.events if _track(ev) in _SOUND_TRACKS]

    # fala em paralelo (a passagem 2 lenta não bloqueia); som é barato, serial.
    from k_nar.tts.batch import synthesize_all
    clips = synthesize_all(voice, speech, workers=4)
    clips.update({ev.id: sfxb.render(ev) for ev in sound})
    # 1ª pessoa: a narração é o protagonista DENTRO da cena → espacializada como fonte.
    timeline = Orquestrador(
        voice, policy, prosody=prosody, scene_model=scene_model,
        spatial_narration=(person == "primeira")).render_scene(scene, clips=clips)

    # PASSAGEM 4 (render + QA)
    samples = {eid: c.samples for eid, c in clips.items()}
    renderer = TimelineRenderer(sr=sr, policy=policy)
    stereo = renderer.render(timeline, samples, mode=mode)
    issues = check_timeline(timeline, policy) + check_mix(dsp.clipping_stats(stereo))
    return RenderResult(stereo=stereo, sr=sr, timeline=timeline, issues=issues,
                        voice_kind=kind, script=script, scene=scene, person=person)
