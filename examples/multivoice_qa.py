"""Fase 2: voz DISTINTA por personagem (modelos Piper reais) + QA acústico.

Cada personagem recebe um `VoiceProfile` apontando para um modelo Piper próprio
(faber e jeff, ambos PT-BR) — timbres genuinamente diferentes, não só um pitch-shift
sobre um locutor único. O roteamento vive no `MultiVoiceTTSBackend`, atrás do mesmo
`TTSBackend`, então o Orquestrador não muda.

Ao final, roda o QA automatizado: checa a EDL (sobreposições que engolem, cortes
agressivos) e a mixagem (clipping/pico). É a rede de segurança antes das camadas
narrativas (narração + SFX + ambiência).

    python -m examples.multivoice_qa [roteiro.json]

Requer as duas vozes:
    scripts/download_piper.sh          # faber
    scripts/download_piper.sh jeff     # jeff
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from k_nar import (Orquestrador, ProsodyPolicy, Scene, TimingPolicy, check_mix,
                   check_timeline, format_report)
from k_nar.director import RuleBasedDirector
from k_nar.render import dsp
from k_nar.render.renderer import TimelineRenderer
from k_nar.render.trim import TrimmedTTS
from k_nar.tts.batch import synthesize_all
from k_nar.tts.cache import CachingTTS
from k_nar.tts.multivoice import MultiVoiceTTSBackend, VoiceProfile

FABER = "models/piper/pt_BR-faber-medium.onnx"
JEFF = "models/piper/pt_BR-jeff-medium.onnx"

# Mapa de elenco: personagem -> voz. Modelos distintos = timbres distintos de verdade.
CAST = {
    "Alien A": VoiceProfile(model_path=FABER),
    "Alien B": VoiceProfile(model_path=JEFF, rate=1.05),  # jeff, um tico mais rápido
}


def _fmt(ms: int) -> str:
    return f"{ms / 1000:6.2f}s"


def main() -> None:
    for path in (FABER, JEFF):
        if not Path(path).exists():
            print(f"voz ausente: {path}\nrode: scripts/download_piper.sh "
                  f"{'jeff' if 'jeff' in path else ''}".rstrip())
            return

    roteiro = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(__file__).parent / "roteiro_exemplo.json"
    scene = Scene.from_dict(RuleBasedDirector().direct(json.loads(roteiro.read_text("utf-8"))))

    prosody = ProsodyPolicy()
    policy = TimingPolicy()
    backend = CachingTTS(TrimmedTTS(MultiVoiceTTSBackend(
        default_model=FABER, profiles=CAST, prosody=prosody)), cache_dir=".knar_cache")

    clips = synthesize_all(backend, scene.events, workers=2)
    timeline = Orquestrador(backend, policy, prosody=prosody).render_scene(scene, clips=clips)
    samples = {eid: c.samples for eid, c in clips.items()}

    print("--- ELENCO ---")
    for ch, prof in CAST.items():
        print(f"  {ch:<10} -> {Path(prof.model_path).stem}  (rate x{prof.rate})")

    print(f"\n--- TIMELINE ({_fmt(timeline.total_duration_ms)}) ---")
    for p in timeline.placements:
        cut = f"  [CORTADA: {p.cut_method}]" if p.hard_cut_ms is not None else ""
        print(f"  {_fmt(p.start_ms)} {_fmt(p.end_ms)} {p.character:<8}{cut}")

    # ---- render + QA ----
    sr = 22050
    renderer = TimelineRenderer(sr=sr, policy=policy)
    stereo = renderer.render(timeline, samples, mode="full")
    out = Path("build_audio"); out.mkdir(exist_ok=True)
    renderer.write_wav(str(out / "multivoice_full.wav"), stereo)

    print("\n--- QA ACÚSTICO ---")
    issues = check_timeline(timeline, policy) + check_mix(dsp.clipping_stats(stereo))
    print(format_report(issues))
    print(f"\naudio: {(out / 'multivoice_full.wav').resolve()}  ({stereo.shape[1]/sr:.2f}s)")


if __name__ == "__main__":
    main()
