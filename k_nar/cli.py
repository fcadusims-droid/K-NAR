"""CLI do K-NAR: história (.md/.txt) → audiobook (.wav). É o que a Action chama.

    python -m k_nar historia.md                     # audiobook em historia.wav
    python -m k_nar historia.md -o saida.wav
    python -m k_nar historia.md --sem-narrador      # modo radiodrama
    python -m k_nar historia.md --idioma en         # sobrescreve o front-matter
    python -m k_nar historia.md --sons sounds/      # usa samples reais (manifest.json)

As flags sobrescrevem o front-matter da história; o front-matter sobrescreve os
defaults. Ver o formato em `docs/TEMPLATE.md`.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path


def _fmt(ms: int) -> str:
    return f"{ms / 1000:6.2f}s"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="k_nar", description="História → audiobook dramatizado.")
    p.add_argument("historia", help="arquivo .md ou .txt da história")
    p.add_argument("-o", "--output", help="arquivo .wav de saída (default: <historia>.wav)")
    p.add_argument("--idioma", "--lang", dest="idioma", help="pt | en | es (sobrescreve o front-matter)")
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--narrador", dest="narrador", action="store_true", default=None,
                     help="força COM narrador")
    grp.add_argument("--sem-narrador", dest="narrador", action="store_false",
                     help="força SEM narrador (radiodrama)")
    p.add_argument("--sons", "--sounds", dest="sons", help="pasta de samples reais (com manifest.json)")
    p.add_argument("--models", default="models/piper", help="pasta dos modelos Piper")
    p.add_argument("--quiet", action="store_true", help="não imprime o resumo")
    return p


def main(argv: list[str] | None = None) -> int:
    from k_nar.pipeline import render_story
    from k_nar.qa import format_report
    from k_nar.story import load_story

    args = build_parser().parse_args(argv)
    src = Path(args.historia)
    if not src.exists():
        print(f"erro: história não encontrada: {src}", file=sys.stderr)
        return 2

    story = load_story(src)
    if args.idioma:
        story = replace(story, lang=args.idioma)
    if args.narrador is not None:
        story = replace(story, narrator=args.narrador)

    out = Path(args.output) if args.output else src.with_suffix(".wav")

    # usa a biblioteca de sons reais automaticamente se existir (sem precisar --sons)
    sons = args.sons
    if sons is None and Path("sounds/manifest.json").exists():
        sons = "sounds"

    try:
        res = render_story(story, models_dir=args.models, sounds_dir=sons)
    except ValueError as e:
        # ex.: história sem nenhuma fala/narração/som após a segmentação
        print(f"erro: não consegui montar a cena ({e}). A história tem conteúdo?",
              file=sys.stderr)
        return 1
    res.write(str(out))

    if not args.quiet:
        n_amb = sum(1 for p in res.timeline.placements if p.track == "ambiencia")
        n_sfx = sum(1 for p in res.timeline.placements if p.track == "sfx")
        n_fala = sum(1 for p in res.timeline.placements if p.track in ("dialogo", "narracao"))
        print(f"história : {story.title!r}  ({story.lang}, "
              f"{'com' if story.narrator else 'sem'} narrador)")
        print(f"voz      : {res.voice_kind}")
        print(f"trilhas  : {n_fala} falas, {n_sfx} SFX, {n_amb} ambiência")
        print(f"duração  : {_fmt(res.timeline.total_duration_ms)}")
        print(format_report(res.issues))
    print(f"áudio    : {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
