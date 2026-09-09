"""Leitor de ROTEIRO — a entrada do K-NAR como narrador de conteúdo.

Um roteiro é um arquivo de texto (`.txt`/`.md`) com um front-matter OPCIONAL e o
corpo em prosa comum — o texto que o narrador deve ler, na ordem, sem inventar nada:

    ---
    titulo: Como o algoritmo do YouTube realmente funciona
    idioma: pt              # pt | en | es
    locutor: Dionisio Schuyler   # locutor de estúdio do XTTS (opcional)
    voz_ref: minha_voz.wav       # OU clona a SUA voz de um sample (opcional)
    velocidade: 1.0              # 1.0 = neutro; 1.1 acelera; 0.9 desacelera
    pausa_paragrafo: 700         # ms de silêncio entre parágrafos
    ---

    Todo mundo acha que sabe como o algoritmo funciona. Quase ninguém sabe.

    Neste vídeo eu vou te mostrar os três sinais que realmente importam.

Nada é obrigatório: um arquivo só com o texto também funciona (defaults: pt, locutor
padrão, velocidade 1.0). O corpo aceita Markdown — cabeçalhos, ênfase, listas e links
são limpos para não serem "lidos" como ruído. Diferente do modo história antigo, aqui
NÃO há inferência de personagens, emoção ou som: o narrador lê o texto como está.

Stdlib puro (sem PyYAML): o front-matter é `chave: valor` por linha. Reaproveita o
parser de front-matter e a limpeza de Markdown do leitor de história.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^﻿?---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """(dict do front-matter, corpo). Sem front-matter → ({}, texto inteiro).

    Stdlib puro (sem PyYAML): o front-matter é `chave: valor` por linha."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        meta[key.strip().lower()] = val.strip().strip('"').strip("'")
    return meta, text[m.end():]


def strip_markdown(text: str) -> str:
    """Remove sintaxe Markdown, preservando a prosa (para não ser 'lida' como ruído).

    Cabeçalhos (`# ...`) são estrutura de roteiro, não narração: são descartados.
    Comentários HTML e blocos de código também (são notas, nunca faladas)."""
    out = text
    out = re.sub(r"<!--.*?-->", " ", out, flags=re.DOTALL)          # comentários HTML (notas)
    out = re.sub(r"```.*?```", " ", out, flags=re.DOTALL)           # blocos de código
    out = re.sub(r"`([^`]*)`", r"\1", out)                          # código inline
    out = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", out)                 # imagens
    out = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", out)              # links -> texto
    lines = []
    for ln in out.splitlines():
        s = ln.strip()
        if s.startswith("#"):                                       # cabeçalhos: estrutura, não fala
            continue
        s = re.sub(r"^\s{0,3}([-*+]|\d+\.)\s+", "", s)              # marcadores de lista
        s = re.sub(r"^\s*>+\s?", "", s)                             # blockquote
        s = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", s)         # negrito/itálico
        s = re.sub(r"^\s*([-*_])\1{2,}\s*$", "", s)                 # regra horizontal
        lines.append(s)
    text = "\n".join(lines)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def _as_float(value: str, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_int(value: str, default: int) -> int:
    try:
        return int(round(float(str(value).strip())))
    except (TypeError, ValueError):
        return default


@dataclass
class Script:
    """Um roteiro pronto para narrar: o texto + as opções de voz e ritmo resolvidas."""

    title: str
    text: str
    lang: str = "pt"
    # Voz: um locutor de estúdio do XTTS (nome) OU um wav de referência p/ clonar a
    # sua própria voz. `voice_ref` tem prioridade sobre `locutor` quando os dois vêm.
    locutor: str = ""
    voice_ref: str = ""
    # Ritmo da leitura.
    speed: float = 1.0
    paragraph_pause_ms: int = 700

    @property
    def slug(self) -> str:
        s = re.sub(r"[^a-z0-9]+", "_", self.title.lower()).strip("_")
        return s or "narracao"


def parse_script(text: str, *, default_lang: str = "pt", title: str = "") -> Script:
    """Constrói um `Script` do conteúdo bruto (front-matter opcional + Markdown)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    meta, body = _parse_frontmatter(text)
    lang = meta.get("idioma", meta.get("language", meta.get("lang", default_lang)))
    ttl = meta.get("titulo", meta.get("title", "")) or title or "narracao"
    return Script(
        title=ttl,
        text=strip_markdown(body),
        lang=str(lang)[:2],
        locutor=meta.get("locutor", meta.get("speaker", "")).strip(),
        voice_ref=meta.get("voz_ref", meta.get("voice_ref", meta.get("ref", ""))).strip(),
        speed=_as_float(meta.get("velocidade", meta.get("speed", "1.0")), 1.0),
        paragraph_pause_ms=_as_int(meta.get("pausa_paragrafo", meta.get("paragraph_pause", "700")), 700),
    )


def load_script(path: str | Path, **overrides) -> Script:
    """Lê um arquivo de roteiro (.txt/.md) e devolve um `Script`."""
    p = Path(path)
    return parse_script(p.read_text("utf-8"), title=p.stem, **overrides)
