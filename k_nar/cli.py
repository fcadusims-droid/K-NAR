"""CLI do K-NAR: roteiro (.txt/.md) → um arquivo de áudio narrado.

O K-NAR é um NARRADOR de conteúdo: você manda o roteiro de um vídeo/post e ele
devolve o áudio completo, narrado por uma voz só, fiel ao texto — sem inventar som,
trilha ou "atuação". É o que a interface web e a GitHub Action chamam.

    python -m k_nar roteiro.txt                       # -> roteiro.wav
    python -m k_nar roteiro.txt -o narracao.wav
    python -m k_nar roteiro.txt --idioma en           # pt | en | es
    python -m k_nar roteiro.txt --velocidade 1.1      # acelera a leitura
    python -m k_nar roteiro.txt --locutor "Dionisio Schuyler"   # locutor de estúdio
    python -m k_nar roteiro.txt --voz-ref minha_voz.wav         # clona a SUA voz
    python -m k_nar roteiro.txt --motor formante      # rascunho offline (sem torch)
    python -m k_nar roteiro.txt --formato opus        # entrega comprimida (.ogg)

As flags sobrescrevem o front-matter do roteiro. Ver o formato em `docs/TEMPLATE.md`.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path


def _fmt(ms: int) -> str:
    s = ms / 1000.0
    return f"{int(s // 60)}m{s % 60:04.1f}s" if s >= 60 else f"{s:.1f}s"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="k_nar", description="Roteiro → áudio narrado.")
    p.add_argument("roteiro", help="arquivo .txt ou .md com o roteiro (o texto a narrar)")
    p.add_argument("-o", "--output", help="arquivo .wav de saída (default: <roteiro>.wav)")
    p.add_argument("--idioma", "--lang", dest="idioma", help="pt | en | es (sobrescreve o front-matter)")
    p.add_argument("--velocidade", "--speed", dest="velocidade", type=float,
                   help="ritmo da leitura (1.0 = neutro; 1.1 acelera; 0.9 desacelera)")
    p.add_argument("--locutor", "--speaker", dest="locutor",
                   help="locutor de estúdio do XTTS (ex.: 'Dionisio Schuyler')")
    p.add_argument("--voz-ref", "--voice-ref", dest="voz_ref",
                   help="wav de referência p/ CLONAR a sua voz (tem prioridade sobre --locutor)")
    p.add_argument("--motor", "--engine", dest="motor", default="xtts",
                   choices=["xtts", "formante"],
                   help="motor de voz: xtts (alta qualidade, padrão) | formante (rascunho offline)")
    p.add_argument("--formato", "--format", dest="formato", default="wav",
                   choices=["wav", "opus", "mp3"],
                   help="wav (padrão) | opus/mp3 (comprimido, sob limite de tamanho)")
    p.add_argument("--max-mb", type=float, default=28.0, help="teto por arquivo p/ opus/mp3")
    p.add_argument("--cache", default=".knar_cache", help="pasta de cache de síntese")
    p.add_argument("--quiet", action="store_true", help="não imprime o resumo")
    return p


def main(argv: list[str] | None = None) -> int:
    from k_nar.narrator import narrate_script
    from k_nar.script import load_script

    args = build_parser().parse_args(argv)
    src = Path(args.roteiro)
    if not src.exists():
        print(f"erro: roteiro não encontrado: {src}", file=sys.stderr)
        return 2

    script = load_script(src)
    if args.idioma:
        script = replace(script, lang=args.idioma)
    if args.velocidade is not None:
        script = replace(script, speed=args.velocidade)
    if args.locutor:
        script = replace(script, locutor=args.locutor)
    if args.voz_ref:
        script = replace(script, voice_ref=args.voz_ref)

    try:
        res = narrate_script(script, engine=args.motor, cache_dir=args.cache)
    except ValueError as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    except ImportError as e:
        print(f"erro: o motor '{args.motor}' precisa de dependências que faltam ({e}).\n"
              f"      instale com: pip install coqui-tts torch   (ou use --motor formante)",
              file=sys.stderr)
        return 1

    out = Path(args.output) if args.output else src.with_suffix(".wav")

    if args.formato == "wav":
        res.write_wav(out)
        outputs = [str(out)]
    else:
        prefix = str(out.with_suffix(""))
        outputs = res.package(prefix, fmt=args.formato, max_mb=args.max_mb)

    if not args.quiet:
        n = len(res.segments)
        print(f"roteiro  : {script.title!r}  ({script.lang})")
        print(f"voz      : {res.voice_kind}"
              + (f"  (clonada de {script.voice_ref})" if script.voice_ref
                 else (f"  (locutor {script.locutor})" if script.locutor else "")))
        print(f"frases   : {n}   velocidade {script.speed:g}")
        print(f"duração  : {_fmt(res.duration_ms)}")
        if res.cache_misses or res.cache_hits:
            print(f"cache    : {res.cache_hits} reaproveitadas, {res.cache_misses} sintetizadas")
    for o in outputs:
        print(f"áudio    : {Path(o).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
