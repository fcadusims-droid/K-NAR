"""Demo do MVP: carrega uma cena (JSON do "Diretor/LLM"), roda o Orquestrador de
Duas Passagens com o TTS mock e imprime a Timeline resultante.

    python -m examples.run_mvp            # usa examples/cena_ponte_comando.json
    python -m examples.run_mvp caminho/da/cena.json

Roda 100% offline, sem nenhuma dependência externa.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from k_nar import MockTTSBackend, Orquestrador, Scene


def _fmt(ms: int) -> str:
    return f"{ms / 1000:6.2f}s"


def main() -> None:
    default = Path(__file__).parent / "cena_ponte_comando.json"
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default

    scene = Scene.from_dict(json.loads(path.read_text(encoding="utf-8")))
    timeline = Orquestrador(MockTTSBackend()).render_scene(scene)

    print(f"\nCENA: {timeline.scene_id}   ambiencia: {timeline.ambiance}")
    print(f"duracao total: {_fmt(timeline.total_duration_ms)}\n")
    print(f"{'inicio':>7}  {'fim':>7}  {'pan':>4}  personagem   fala")
    print("-" * 72)
    for p in timeline.placements:
        cut = "  [INTERROMPIDA]" if p.hard_cut_ms is not None else ""
        end = p.end_ms
        print(
            f"{_fmt(p.start_ms)}  {_fmt(end)}  {p.pan:>4}  "
            f"{p.character:<11}  {p.text}{cut}"
        )

    overlaps = timeline.overlaps()
    if overlaps:
        print("\nsobreposicoes detectadas (QA):")
        for a, b, ms in overlaps:
            print(f"  {a} x {b}: {ms} ms")


if __name__ == "__main__":
    main()
