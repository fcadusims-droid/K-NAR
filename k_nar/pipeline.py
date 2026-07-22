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

    def write(self, path: str) -> str:
        from k_nar.render.renderer import TimelineRenderer
        TimelineRenderer(sr=self.sr).write_wav(str(path), self.stereo)
        return str(path)


def _voice_backend(lang_profile, prosody, models_dir: str):
    """Piper (por idioma) se os modelos existirem; senão, formante sintético."""
    main = Path(models_dir) / lang_profile.main_voice
    if main.exists():
        from k_nar.render.trim import TrimmedTTS
        from k_nar.tts.cache import CachingTTS
        from k_nar.tts.multivoice import MultiVoiceTTSBackend, VoiceProfile
        narr = Path(models_dir) / lang_profile.narrator_voice
        profiles = {"Narrador": VoiceProfile(
            model_path=str(narr if narr.exists() else main))}
        mv = MultiVoiceTTSBackend(default_model=str(main), profiles=profiles, prosody=prosody)
        return CachingTTS(TrimmedTTS(mv), cache_dir=".knar_cache"), 22050, "piper"
    from k_nar.render.voice import FormantTTSBackend
    return FormantTTSBackend(sr=24000), 24000, "formante"


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
                 sounds_dir: str | None = None, mode: str = "full") -> RenderResult:
    """Roda a cadeia completa Screenwriter → Director → Orquestrador → Renderer."""
    from k_nar import (Orquestrador, ProsodyPolicy, Scene, TimingPolicy, check_mix,
                       check_timeline)
    from k_nar.director import RuleBasedDirector
    from k_nar.narrative import RuleBasedScreenwriter
    from k_nar.render import dsp
    from k_nar.render.renderer import TimelineRenderer

    lang_profile = get_language(story.lang)

    # PASSAGEM 0 → 1
    script = RuleBasedScreenwriter().write(
        story.prose, scene_id=story.scene_id, ambiance=story.ambiance,
        narrator=story.narrator, lang=story.lang)
    scene = Scene.from_dict(RuleBasedDirector().direct(script))

    # PASSAGENS 2-3
    prosody = ProsodyPolicy()
    policy = TimingPolicy()
    voice, sr, kind = _voice_backend(lang_profile, prosody, models_dir)
    sfxb = _sfx_backend(sr, sounds_dir)

    clips = {}
    for ev in scene.events:
        track = getattr(getattr(ev, "track", None), "value", "dialogo")
        clips[ev.id] = sfxb.render(ev) if track in _SOUND_TRACKS else voice.synthesize(ev)
    timeline = Orquestrador(voice, policy, prosody=prosody).render_scene(scene, clips=clips)

    # PASSAGEM 4 (render + QA)
    samples = {eid: c.samples for eid, c in clips.items()}
    renderer = TimelineRenderer(sr=sr, policy=policy)
    stereo = renderer.render(timeline, samples, mode=mode)
    issues = check_timeline(timeline, policy) + check_mix(dsp.clipping_stats(stereo))
    return RenderResult(stereo=stereo, sr=sr, timeline=timeline, issues=issues, voice_kind=kind)
