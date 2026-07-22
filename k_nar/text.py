"""Utilitários de texto compartilhados (stdlib puro).

`strip_accents` é a fonte ÚNICA da normalização usada pelo Screenwriter e pelo
Director (antes duplicada como `_norm` em cada um). Remove acentos e caixa para
casar palavras-gatilho de forma robusta em PT/ES/EN.
"""

from __future__ import annotations

_ACCENTS = str.maketrans(
    "áàâãäéèêëíìîïóòôõöúùûüçñ",
    "aaaaaeeeeiiiiooooouuuucn",
)


def strip_accents(text: str) -> str:
    """minúsculas + sem acentos (á→a, ó→o, ç→c, ñ→n)."""
    return text.lower().translate(_ACCENTS)
