"""HISTÓRIA em prosa → AUDIODRAMA (vozes + SFX + ambiência), com o breakdown das passagens.

Demo verboso do pipeline: mostra como o Screenwriter (PASSAGEM 0) classifica cada
frase e como a EDL multitrack fica, e então renderiza. Para o uso "de verdade",
prefira a CLI: `python -m k_nar historia.md`.

    python -m examples.story_to_audio [historia.md|.txt] [--sem-narrador] [--idioma en]

Usa `k_nar.pipeline.render_story` por baixo (a mesma cadeia da CLI e da GitHub Action).
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

from k_nar import Track
from k_nar.pipeline import render_story
from k_nar.qa import format_report
from k_nar.story import load_story


def _fmt(ms: int) -> str:
    return f"{ms / 1000:6.2f}s"


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src = Path(args[0]) if args else Path(__file__).parent / "historia_template.md"
    story = load_story(src)
    if "--sem-narrador" in sys.argv:
        story = replace(story, narrator=False)
    if "--idioma" in sys.argv:
        story = replace(story, lang=sys.argv[sys.argv.index("--idioma") + 1])

    res = render_story(story)

    print(f"--- HISTÓRIA: {story.title!r}  ({story.lang}, "
          f"{'com' if story.narrator else 'sem'} narrador) ---")
    print(f"[PASSAGEM 0] Screenwriter → {len(res.script['elementos'])} elementos")
    for el in res.script["elementos"]:
        icon = {"fala": "💬", "narracao": "🎙️", "sfx": "🔊", "ambiencia": "🌲"}.get(el["tipo"], "?")
        who = el.get("personagem") or el.get("tag") or ""
        print(f"  {icon} {el['tipo']:<9} {who:<14} {el.get('texto','')[:50]!r}")

    print(f"\n--- TIMELINE MULTITRACK ({_fmt(res.timeline.total_duration_ms)}) — voz: {res.voice_kind} ---")
    for p in res.timeline.placements:
        icon = {"dialogo": "💬", "narracao": "🎙️", "sfx": "🔊", "ambiencia": "🌲"}.get(p.track, "?")
        span = "cena inteira" if p.track == Track.AMBIENCE.value else f"{_fmt(p.start_ms)}→{_fmt(p.end_ms)}"
        print(f"  {icon} {p.track:<10} {span:<22} {p.character or p.text}")

    out = Path("build_audio"); out.mkdir(exist_ok=True)
    res.write(str(out / "audiodrama.wav"))
    print(f"\n--- QA ---\n{format_report(res.issues)}")
    print(f"\naudio: {(out / 'audiodrama.wav').resolve()}  ({res.stereo.shape[1]/res.sr:.2f}s)")


if __name__ == "__main__":
    main()
