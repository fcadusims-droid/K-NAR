"""Pipeline COMPLETO: roteiro cru -> Director (PASSAGEM 1) -> Orquestrador -> audio.

    python -m examples.direct_and_render [roteiro.json] [--llm]

Sem --llm usa o RuleBasedDirector (heuristico, sem modelo). Com --llm usa o
LlamaDirector se o modelo GGUF existir em models/ (cai nas regras se faltar).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from k_nar import Orquestrador, Scene, TimingPolicy
from k_nar.director import RuleBasedDirector
from k_nar.render.renderer import TimelineRenderer
from k_nar.render.trim import TrimmedTTS
from k_nar.render.voice import FormantTTSBackend

SR = 24000
MODEL = Path("models/qwen2.5-1.5b-instruct-q4_k_m.gguf")


def _fmt(ms: int) -> str:
    return f"{ms / 1000:6.2f}s"


def _make_director(use_llm: bool):
    if use_llm and MODEL.exists():
        try:
            from k_nar.director.llama import LlamaDirector
            print(f"[director] LLM local: {MODEL.name}")
            return LlamaDirector(str(MODEL), n_threads=4)
        except Exception as e:  # pragma: no cover
            print(f"[director] LLM indisponivel ({e}); usando regras")
    print("[director] RuleBasedDirector (heuristico)")
    return RuleBasedDirector()


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--llm"]
    use_llm = "--llm" in sys.argv
    roteiro_path = Path(args[0]) if args else Path(__file__).parent / "roteiro_exemplo.json"
    out_dir = Path(args[1]) if len(args) > 1 else Path("build_audio")

    script = json.loads(roteiro_path.read_text(encoding="utf-8"))
    director = _make_director(use_llm)

    # PASSAGEM 1: roteiro cru -> JSON de metadados relativos (validado no schema)
    scene_dict = director.direct(script)
    print("\n--- PASSAGEM 1 (metadados gerados) ---")
    for ev in scene_dict["eventos"]:
        print(f"  {ev['personagem']:<8} tensao={ev['voz']['tensao']:<7} "
              f"entrada={ev['entrada']['tipo']:<12} agg={ev['entrada']['agressividade']:<4} "
              f"pausa={ev['saida']['pausa']:<6} | {ev['texto'][:44]}")

    # PASSAGENS 2+3: timeline
    scene = Scene.from_dict(scene_dict)
    backend = TrimmedTTS(FormantTTSBackend(sr=SR))
    timeline = Orquestrador(backend, TimingPolicy()).render_scene(scene)
    clips = {e.id: backend.synthesize(e).samples for e in scene.events}

    print(f"\n--- TIMELINE ({_fmt(timeline.total_duration_ms)}) ---")
    for p in timeline.placements:
        cut = "  [CORTADA]" if p.hard_cut_ms is not None else ""
        print(f"  {_fmt(p.start_ms)} {_fmt(p.end_ms)} pan={p.pan:>4} {p.character:<8}{cut}")

    # PASSAGEM 4: render
    out_dir.mkdir(parents=True, exist_ok=True)
    renderer = TimelineRenderer(sr=SR, policy=TimingPolicy())
    stereo = renderer.render(timeline, clips, mode="full")
    path = out_dir / "roteiro_full.wav"
    renderer.write_wav(str(path), stereo)
    print(f"\naudio: {path.resolve()}  ({stereo.shape[1]/SR:.2f}s)")


if __name__ == "__main__":
    main()
