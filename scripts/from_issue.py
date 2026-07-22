"""Monta uma história (`story.md`) a partir de um GitHub Issue Form ou de inputs de
workflow_dispatch. Chamado pela GitHub Action.

Issue Form: o corpo vem em `ISSUE_BODY`, com seções `### <rótulo>` (Título, Idioma,
Narrador, História). workflow_dispatch: os campos vêm em WD_STORY/WD_LANG/WD_NARR.

Escreve `story.md` (front-matter + prosa) e `run_lang.txt` (idioma resolvido, p/ o
download da voz). Stdlib puro.
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
        title = _pick(f, "titulo", "title") or "historia"
        lang = _pick(f, "idioma", "language", "lang") or "pt"
        narrador_raw = _pick(f, "narrador", "narrator")
        story = _pick(f, "historia", "story", "texto")
    else:
        title = os.environ.get("WD_TITLE", "historia") or "historia"
        lang = os.environ.get("WD_LANG", "pt") or "pt"
        narrador_raw = os.environ.get("WD_NARR", "com")
        story = os.environ.get("WD_STORY", "")

    lang = _norm(lang).split("_")[0].split("-")[0]
    if lang not in _LANGS:
        lang = "pt"
    narrador = "nao" if "sem" in _norm(narrador_raw) or _norm(narrador_raw) in ("nao", "no", "false") else "sim"

    if not story.strip():
        raise SystemExit("erro: história vazia")

    front = (f"---\ntitulo: {title}\nidioma: {lang}\nnarrador: {narrador}\n---\n\n")
    with open("story.md", "w", encoding="utf-8") as fh:
        fh.write(front + story.strip() + "\n")
    with open("run_lang.txt", "w", encoding="utf-8") as fh:
        fh.write(lang)
    print(f"[from_issue] titulo={title!r} idioma={lang} narrador={narrador} "
          f"({len(story)} chars)")


if __name__ == "__main__":
    main()
