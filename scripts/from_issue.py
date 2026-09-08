"""Monta um roteiro (`roteiro.md`) a partir de um GitHub Issue Form ou de inputs de
workflow_dispatch. Chamado pela GitHub Action do narrador.

Issue Form: o corpo vem em `ISSUE_BODY`, com seções `### <rótulo>` (Título, Idioma,
Roteiro). workflow_dispatch: os campos vêm em WD_TITLE/WD_LANG/WD_SCRIPT.

Escreve `roteiro.md` (front-matter + texto). Stdlib puro.
"""

from __future__ import annotations

import os
import re
import unicodedata

_LANGS = {"pt", "en", "es"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
    return s.strip().lower()


def _parse_issue_form(body: str) -> dict[str, str]:
    """Seções '### Rótulo\\n<valor>' -> {rótulo_normalizado: valor}."""
    fields: dict[str, str] = {}
    parts = re.split(r"^###\s+", body or "", flags=re.MULTILINE)
    for part in parts:
        if "\n" not in part:
            continue
        label, _, value = part.partition("\n")
        value = value.strip()
        if value in ("_No response_", "_Sem resposta_", ""):
            continue
        fields[_norm(label)] = value
    return fields


def _pick(fields: dict[str, str], *keys: str) -> str:
    for k in fields:
        if any(kw in k for kw in keys):
            return fields[k]
    return ""


def main() -> None:
    body = os.environ.get("ISSUE_BODY", "")
    if body:
        f = _parse_issue_form(body)
        title = _pick(f, "titulo", "title") or "narracao"
        lang = _pick(f, "idioma", "language", "lang") or "pt"
        script = _pick(f, "roteiro", "script", "texto", "text")
    else:
        title = os.environ.get("WD_TITLE", "narracao") or "narracao"
        lang = os.environ.get("WD_LANG", "pt") or "pt"
        script = os.environ.get("WD_SCRIPT", "")

    lang = _norm(lang).split("_")[0].split("-")[0]
    if lang not in _LANGS:
        lang = "pt"

    if not script.strip():
        raise SystemExit("erro: roteiro vazio")

    front = f"---\ntitulo: {title}\nidioma: {lang}\n---\n\n"
    with open("roteiro.md", "w", encoding="utf-8") as fh:
        fh.write(front + script.strip() + "\n")
    print(f"[from_issue] titulo={title!r} idioma={lang} ({len(script)} chars)")


if __name__ == "__main__":
    main()
