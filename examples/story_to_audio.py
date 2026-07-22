"""Fase 5: HISTÓRIA em prosa → AUDIODRAMA completo (vozes + SFX + ambiência).

    prosa .txt
       │  PASSAGEM 0  Screenwriter   (narração / diálogo / SFX / ambiência)
       ▼                              — descrição sonora vira SOM, não narração;
    roteiro estruturado                 narrador é OPCIONAL (--sem-narrador)
       │  PASSAGEM 1  Director        (tensão / entrada / pausa por fala)
       ▼
    cena (fala + som, validada)
       │  PASSAGENS 2-3  Orquestrador  (fala→TTS, som→SfxBackend; EDL multitrack)
       ▼
    Timeline  ──►  Renderer (DUCKING)  ──►  audiodrama
       (ambiência/SFX afundam sob a fala; um som não estraga o outro)

    python -m examples.story_to_audio [historia.txt] [--sem-narrador]

Sons: `ProceduralSfxBackend` (síntese, sem baixar nada) por padrão; troque por
`LibrarySfxBackend(manifest)` para usar samples REAIS. Vozes: Piper se houver
modelos, senão formante.
"""

from __future__ import annotations

import sys
from pathlib import Path

from k_nar import (Orquestrador, ProsodyPolicy, Scene, TimingPolicy, Track,
                   check_mix, check_timeline, format_report)
from k_nar.director import RuleBasedDirector
from k_nar.narrative import RuleBasedScreenwriter
from k_nar.render import dsp
from k_nar.render.renderer import TimelineRenderer
from k_nar.sfx import ProceduralSfxBackend

FABER = "models/piper/pt_BR-faber-medium.onnx"
JEFF = "models/piper/pt_BR-jeff-medium.onnx"
_SOUND_TRACKS = {Track.SFX.value, Track.AMBIENCE.value}


def _voice_backend(prosody, sr_hint=22050):
    if Path(FABER).exists():
        from k_nar.tts.cache import CachingTTS
        from k_nar.tts.multivoice import MultiVoiceTTSBackend, VoiceProfile
        from k_nar.render.trim import TrimmedTTS
        profiles = {"Narrador": VoiceProfile(model_path=JEFF if Path(JEFF).exists() else FABER)}
        mv = MultiVoiceTTSBackend(default_model=FABER, profiles=profiles, prosody=prosody)
        return CachingTTS(TrimmedTTS(mv), cache_dir=".knar_cache"), 22050, "piper"
    from k_nar.render.voice import FormantTTSBackend
    return FormantTTSBackend(sr=24000), 24000, "formante"


def _fmt(ms: int) -> str:
    return f"{ms / 1000:6.2f}s"


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    narrator = "--sem-narrador" not in sys.argv
    historia = Path(args[0]) if args else Path(__file__).parent / "historia_sonora.txt"
    prose = historia.read_text("utf-8").strip()

    # PASSAGEM 0
    script = RuleBasedScreenwriter().write(
        prose, scene_id=historia.stem, ambiance="cockpit_metalico_eco", narrator=narrator)
    print(f"--- PASSAGEM 0: Screenwriter (narrador={'on' if narrator else 'OFF'}) ---")
    for el in script["elementos"]:
        icon = {"fala": "💬", "narracao": "🎙️", "sfx": "🔊", "ambiencia": "🌲"}.get(el["tipo"], "?")
        who = el.get("personagem") or el.get("tag") or ""
        print(f"  {icon} {el['tipo']:<9} {who:<14} {el.get('texto','')[:52]!r}")

    # PASSAGEM 1
    scene = Scene.from_dict(RuleBasedDirector().direct(script))

    # PASSAGENS 2-3: fala via TTS, som via SfxBackend
    prosody = ProsodyPolicy()
    policy = TimingPolicy()
    voice, sr, kind = _voice_backend(prosody)
    sfxb = ProceduralSfxBackend(sr=sr)
    print(f"\n[voz] {kind}   [som] procedural")

    clips = {}
    for ev in scene.events:
        clips[ev.id] = sfxb.render(ev) if _track_name(ev) in _SOUND_TRACKS else voice.synthesize(ev)
    timeline = Orquestrador(voice, policy, prosody=prosody).render_scene(scene, clips=clips)
    samples = {eid: c.samples for eid, c in clips.items()}

    print(f"\n--- TIMELINE MULTITRACK ({_fmt(timeline.total_duration_ms)}) ---")
    for p in timeline.placements:
        icon = {"dialogo": "💬", "narracao": "🎙️", "sfx": "🔊", "ambiencia": "🌲"}.get(p.track, "?")
        span = "cena inteira" if p.track == "ambiencia" else f"{_fmt(p.start_ms)}→{_fmt(p.end_ms)}"
        print(f"  {icon} {p.track:<10} {span:<22} {p.character or p.text}")

    renderer = TimelineRenderer(sr=sr, policy=policy)
    stereo = renderer.render(timeline, samples, mode="full")
    out = Path("build_audio"); out.mkdir(exist_ok=True)
    renderer.write_wav(str(out / "audiodrama.wav"), stereo)

    print("\n--- QA ---")
    issues = check_timeline(timeline, policy) + check_mix(dsp.clipping_stats(stereo))
    print(format_report(issues))
    print(f"\naudio: {(out / 'audiodrama.wav').resolve()}  ({stereo.shape[1]/sr:.2f}s)")


def _track_name(ev) -> str:
    t = getattr(ev, "track", None)
    return getattr(t, "value", t) or "dialogo"


if __name__ == "__main__":
    main()
