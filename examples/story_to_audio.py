"""Fase 4: HISTÓRIA em prosa → audiobook dramatizado (a cadeia completa).

    prosa .txt
       │  PASSAGEM 0  Screenwriter  (segmenta narração / diálogo / ações)
       ▼
    roteiro estruturado
       │  PASSAGEM 1  Director       (dá tensão / entrada / pausa por elemento)
       ▼
    cena JSON (narração + diálogo, validada)
       │  PASSAGENS 2-3  Orquestrador (duração real → EDL multitrack)
       ▼
    Timeline  ──►  Renderer  ──►  áudio narrado (narrador + vozes, trilhas separadas)

    python -m examples.story_to_audio [historia.txt]

Usa Piper se as vozes existirem (narrador→jeff, personagens→faber); senão, formante
sintético (sem baixar nada). As "ações" detectadas viram sementes de SFX (Fase 5).
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

FABER = "models/piper/pt_BR-faber-medium.onnx"
JEFF = "models/piper/pt_BR-jeff-medium.onnx"


def _backend(prosody):
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
    historia = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(__file__).parent / "historia_exemplo.txt"
    prose = historia.read_text("utf-8").strip()

    # PASSAGEM 0: prosa → roteiro estruturado
    script = RuleBasedScreenwriter().write(
        prose, scene_id=historia.stem, ambiance="cockpit_metalico_eco")
    print("--- PASSAGEM 0: Screenwriter ---")
    for el in script["elementos"]:
        tag = "🎙️ NARR" if el["tipo"] == "narracao" else f"💬 {el.get('personagem','?')}"
        deixa = f"  ({el['deixa']})" if el.get("deixa") else ""
        print(f"  {tag:<14} {el['texto']!r}{deixa}")
    if script["acoes"]:
        print("  ações→SFX (Fase 5):", [a["gatilho"] for a in script["acoes"]])

    # PASSAGEM 1: Director
    scene_dict = RuleBasedDirector().direct(script)
    scene = Scene.from_dict(scene_dict)

    # PASSAGENS 2-3: Orquestrador
    prosody = ProsodyPolicy()
    policy = TimingPolicy()
    backend, sr, kind = _backend(prosody)
    print(f"\n[tts] {kind}")
    # sintetiza UMA vez e passa os clips à passagem 3 (a timeline nunca re-sintetiza;
    # evita duplicar a síntese e garante que timeline e áudio usem o MESMO clip).
    clips = {ev.id: backend.synthesize(ev) for ev in scene.events}
    timeline = Orquestrador(backend, policy, prosody=prosody).render_scene(scene, clips=clips)
    samples = {eid: c.samples for eid, c in clips.items()}

    print(f"\n--- TIMELINE MULTITRACK ({_fmt(timeline.total_duration_ms)}) ---")
    for p in timeline.placements:
        faixa = "🎙️" if p.track == Track.NARRATION.value else "💬"
        cut = f"  [corte: {p.cut_method}]" if p.hard_cut_ms is not None else ""
        print(f"  {_fmt(p.start_ms)} {_fmt(p.end_ms)} {faixa} {p.character:<11}{cut}")

    renderer = TimelineRenderer(sr=sr, policy=policy)
    stereo = renderer.render(timeline, samples, mode="full")
    out = Path("build_audio"); out.mkdir(exist_ok=True)
    renderer.write_wav(str(out / "story_full.wav"), stereo)

    print("\n--- QA ---")
    issues = check_timeline(timeline, policy) + check_mix(dsp.clipping_stats(stereo))
    print(format_report(issues))
    print(f"\naudio: {(out / 'story_full.wav').resolve()}  ({stereo.shape[1]/sr:.2f}s)")


if __name__ == "__main__":
    main()
