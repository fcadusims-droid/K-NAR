"""Baixa uma biblioteca de EFEITOS SONOROS reais (ESC-50), ciente de LICENÇA.

O ESC-50 (https://github.com/karoldvl/ESC-50) é um dataset de 2000 clipes em 50
categorias de som ambiente — grilos, trovão, chuva, porta rangendo, passos, vidro
quebrando, relógio, sirene, motor, sinos... quase um mapa 1:1 do que um áudio
narrativo precisa. O conjunto é CC BY-NC, MAS cada clipe tem licença própria (muitos
CC0/CC-BY). Este script PREFERE clipes CC0/CC-BY e registra a atribuição.

    python scripts/download_sfx.py                 # ~4 clipes por categoria usada
    python scripts/download_sfx.py --free-only     # só CC0/CC-BY (uso comercial ok)
    python scripts/download_sfx.py --per-tag 6 --dest sounds

Gera:
    sounds/esc50/<categoria>/*.wav   — os samples
    sounds/manifest.json             — tag do K-NAR -> [arquivos]  (o LibrarySfxBackend lê)
    sounds/ATTRIBUTION.md            — licença + autor + fonte de cada clipe
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from k_nar.sfx.catalog import ESC50_CATEGORIES  # noqa: E402

_RAW = "https://raw.githubusercontent.com/karoldvl/ESC-50/master"
# preferência de licença (menor = mais livre). --free-only mantém só <= 1.
_LICENSE_RANK = {"CC0": 0, "CC-BY": 1, "CC-BY-SA": 1,
                 "CC-BY-NC": 2, "CC-BY-NC-SA": 2, "CC-Sampling+": 2}
_LIC_RE = re.compile(
    r"\[([\w.\-]+?)\.(?:ogg|wav|aiff?|flac)\]:\s*clip derived from .*?"
    r"\((https?://[^)]+)\)\s*by\s*(.+?)\s*\[([\w+\-]+)\]", re.IGNORECASE)


def _curl(url: str) -> bytes:
    out = subprocess.run(["curl", "-fsSL", url], capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(f"falha ao baixar {url}: {out.stderr.decode()[:200]}")
    return out.stdout


def _stem(filename: str) -> str:
    """'1-100032-A-0.wav' -> '1-100032-A' (casa com o id da licença)."""
    m = re.match(r"^(.*)-\d+\.wav$", filename)
    return m.group(1) if m else filename


def _load_meta() -> dict[str, str]:
    import csv
    import io
    text = _curl(f"{_RAW}/meta/esc50.csv").decode("utf-8")
    return {r["filename"]: r["category"] for r in csv.DictReader(io.StringIO(text))}


def _load_licenses() -> dict[str, tuple[str, str, str]]:
    """stem -> (licença, autor, url). Do bloco de atribuição do LICENSE."""
    text = _curl(f"{_RAW}/LICENSE").decode("utf-8")
    out: dict[str, tuple[str, str, str]] = {}
    for m in _LIC_RE.finditer(text):
        stem, url, author, lic = m.group(1), m.group(2), m.group(3).strip(), m.group(4).upper()
        out[stem] = (lic, author, url)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Baixa SFX reais (ESC-50) por licença.")
    ap.add_argument("--per-tag", type=int, default=4, help="clipes por categoria (default 4)")
    ap.add_argument("--free-only", action="store_true", help="só CC0/CC-BY (comercial ok)")
    ap.add_argument("--dest", default="sounds", help="pasta de saída (default sounds/)")
    args = ap.parse_args()

    dest = Path(args.dest)
    print("[sfx] lendo metadados e licenças do ESC-50...")
    meta = _load_meta()
    licenses = _load_licenses()

    # categoria ESC-50 -> [(filename, licença, autor, url)]
    by_cat: dict[str, list[tuple[str, str, str, str]]] = {}
    for fn, cat in meta.items():
        lic, author, url = licenses.get(_stem(fn), ("desconhecida", "?", ""))
        by_cat.setdefault(cat, []).append((fn, lic, author, url))

    manifest: dict[str, list[str]] = {}
    attribution: list[str] = []
    total = 0

    for cat in sorted(ESC50_CATEGORIES):
        clips = by_cat.get(cat, [])
        # ordena por preferência de licença; --free-only descarta NC/desconhecida
        ranked = sorted(clips, key=lambda c: _LICENSE_RANK.get(c[1], 3))
        if args.free_only:
            ranked = [c for c in ranked if _LICENSE_RANK.get(c[1], 3) <= 1]
        chosen = ranked[: args.per_tag]
        if not chosen:
            print(f"[sfx] AVISO: sem clipes elegíveis para '{cat}' (pulando)")
            continue

        outdir = dest / "esc50" / cat
        outdir.mkdir(parents=True, exist_ok=True)
        rels: list[str] = []
        for fn, lic, author, url in chosen:
            path = outdir / fn
            if not path.exists():
                path.write_bytes(_curl(f"{_RAW}/audio/{fn}"))
                total += 1
            rel = str(path.relative_to(dest))
            rels.append(rel)
            attribution.append(f"- `{rel}` — {lic}, por {author} ({url})")

        for tag in ESC50_CATEGORIES[cat]:
            manifest[tag] = rels
        print(f"[sfx] {cat:<18} {len(chosen)} clipe(s) -> {', '.join(ESC50_CATEGORIES[cat])}")

    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), "utf-8")
    (dest / "ATTRIBUTION.md").write_text(
        "# Atribuição dos efeitos sonoros\n\n"
        "Clipes do [ESC-50](https://github.com/karoldvl/ESC-50) (Piczak, 2015). O "
        "conjunto é CC BY-NC; cada clipe tem a licença abaixo. Use `--free-only` para "
        "só CC0/CC-BY.\n\n" + "\n".join(sorted(set(attribution))) + "\n", "utf-8")

    print(f"\n[sfx] ok: {total} arquivo(s) novo(s), {len(manifest)} tags em "
          f"{dest}/manifest.json  (atribuição em {dest}/ATTRIBUTION.md)")


if __name__ == "__main__":
    main()
