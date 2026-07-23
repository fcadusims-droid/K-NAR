"""Detecção da PESSOA narrativa: 1ª pessoa (o personagem conta) vs 3ª (um narrador).

Por que importa para o áudio: em 3ª pessoa o narrador é ONISCIENTE — uma voz de fora
da cena, seca e íntima, que não está "no cômodo". Em 1ª pessoa a narração É o
protagonista falando — a mesma voz do personagem, DENTRO da cena (leva o reverb do
cômodo, como qualquer fonte). O K-NAR trata os dois casos diferente no mix.

A detecção é feita SÓ sobre o texto de narração (o diálogo sempre tem "eu", então
contaria pessoa errada). Conta pronomes de 1ª vs 3ª pessoa do léxico do idioma.
"""

from __future__ import annotations

import re

from k_nar.narrative.lexicons import get_lexicon
from k_nar.text import strip_accents as _norm

_WORD = re.compile(r"[0-9A-Za-zÀ-ÿ]+")

PRIMEIRA = "primeira"
TERCEIRA = "terceira"


def detect_person(narration_text: str, lang: str = "pt") -> str:
    """"primeira" se a narração é contada em 1ª pessoa; "terceira" caso contrário.

    Heurística honesta: conta marcadores de 1ª pessoa ("eu/meu") vs 3ª ("ele/ela") na
    narração. 1ª pessoa vence quando aparece e supera a 3ª — senão o padrão é 3ª
    pessoa (o caso mais comum e o comportamento anterior do motor)."""
    lex = get_lexicon(lang)
    if not lex.first_person and not lex.third_person:
        return TERCEIRA
    first = third = 0
    for w in _WORD.findall(narration_text or ""):
        n = _norm(w)
        if n in lex.first_person:
            first += 1
        elif n in lex.third_person:
            third += 1
    return PRIMEIRA if first > third and first > 0 else TERCEIRA


def resolve_person(value: str) -> str:
    """Normaliza o valor de front-matter/CLI para "primeira"/"terceira"/"auto"."""
    v = str(value or "auto").strip().lower()
    if v in ("1", "primeira", "primeira_pessoa", "eu", "first", "first_person", "1a", "1ª"):
        return PRIMEIRA
    if v in ("3", "terceira", "terceira_pessoa", "narrador", "third", "third_person", "3a", "3ª"):
        return TERCEIRA
    return "auto"
