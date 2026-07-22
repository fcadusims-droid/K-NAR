"""Fase 3: cena NARRADA (narração + diálogo em trilhas separadas) → áudio multitrack.

Prova que a EDL generalizada suporta narração e diálogo em buses distintos: o
narrador tem voz e trilha próprias (`Track.NARRATION`), os personagens ficam na
trilha de diálogo. O renderer mixa por trilha e combina — a estrutura que o ducking
(Fase 5) vai usar para a ambiência afundar sob a fala.

    python -m examples.narrated_scene [roteiro.json]

Usa Piper se as vozes existirem (narrador→jeff, personagens→faber); sem elas, cai no
FormantTTSBackend (sintético, sem baixar nada) — a estrutura multitrack é a mesma.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from k_nar import (Orquestrador, ProsodyPolicy, Scene, TimingPolicy, Track,
                   check_mix, check_timeline, format_report)
from k_nar.render import dsp
from k_nar.render.renderer import TimelineRenderer

FABER = "models/piper/pt_BR-faber-medium.onnx"
JEFF = "models/piper/pt_BR-jeff-medium.onnx"


def _backend(prosody):
    """Piper multivoz se houver modelos; senão, formante sintético (sem download)."""
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
    roteiro = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(__file__).parent / "roteiro_narrado.json"
    scene = Scene.from_dict(json.loads(roteiro.read_text("utf-8")))

    prosody = ProsodyPolicy()
    policy = TimingPolicy()
    backend, sr, kind = _backend(prosody)
    print(f"[tts] {kind}")

    # sintetiza UMA vez e passa os clips à passagem 3 (timeline e áudio usam o mesmo
    # clip; sem re-síntese duplicada).
    clips = {ev.id: backend.synthesize(ev) for ev in scene.events}
    timeline = Orquestrador(backend, policy, prosody=prosody).render_scene(scene, clips=clips)
    samples = {eid: c.samples for eid, c in clips.items()}

    print(f"\n--- TIMELINE MULTITRACK ({_fmt(timeline.total_duration_ms)}) ---")
    for p in timeline.placements:
        cut = f"  [CORTADA: {p.cut_method}]" if p.hard_cut_ms is not None else ""
        faixa = "🎙️ NARR " if p.track == Track.NARRATION.value else "💬 DIAL "
        print(f"  {_fmt(p.start_ms)} {_fmt(p.end_ms)} {faixa} {p.character:<8}{cut}")

    tracks = sorted({p.track for p in timeline.placements})
    print(f"\ntrilhas na EDL: {tracks}")

    renderer = TimelineRenderer(sr=sr, policy=policy)
    stereo = renderer.render(timeline, samples, mode="full")
    out = Path("build_audio"); out.mkdir(exist_ok=True)
    renderer.write_wav(str(out / "narrated_full.wav"), stereo)

    print("\n--- QA ---")
    issues = check_timeline(timeline, policy) + check_mix(dsp.clipping_stats(stereo))
    print(format_report(issues))
    print(f"\naudio: {(out / 'narrated_full.wav').resolve()}  ({stereo.shape[1]/sr:.2f}s)")


if __name__ == "__main__":
    main()
