"""Leitor de HISTÓRIA — o formato de entrada do K-NAR (o "template padrão").

Uma história é um arquivo de texto (`.md` ou `.txt`) com um front-matter YAML-leve
OPCIONAL e o corpo em prosa comum:

    ---
    titulo: A Ponte de Comando
    idioma: pt              # pt | en | es
    narrador: sim           # sim/nao (ou true/false, com/sem)
    ambientacao: cockpit_metalico_eco
    ---

    A nave cortava o vazio... "Tem alguem ai?", perguntou a Comandante.

Nada disso é obrigatório: um `.md` só com prosa também funciona (defaults: pt, com
narrador, ambiência seca). O corpo aceita Markdown — cabeçalhos, ênfase, listas e
links são limpos para não serem "lidos" como pontuação. O front-matter só define as
opções; a segmentação em narração/diálogo/som é do Screenwriter (PASSAGEM 0).

Este módulo é stdlib puro (sem PyYAML): o front-matter é `chave: valor` por linha.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_TRUE = {"sim", "s", "true", "yes", "y", "com", "1", "on"}
_FALSE = {"nao", "não", "n", "false", "no", "sem", "0", "off"}

_FRONTMATTER_RE = re.compile(r"^﻿?---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Story:
    """História pronta para o pipeline: prosa + opções resolvidas."""

    title: str
    prose: str
    lang: str = "pt"
    narrator: bool = True
    ambiance: str = "seco"

    @property
    def scene_id(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", self.title.lower()).strip("_")
        return slug or "cena"


def _parse_bool(value: str, default: bool) -> bool:
    v = str(value).strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return default


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """(dict do front-matter, corpo). Sem front-matter → ({}, texto inteiro)."""
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
    """Remove sintaxe Markdown, preservando a prosa (para não ser 'lida' como ruído)."""
    out = text
    out = re.sub(r"```.*?```", " ", out, flags=re.DOTALL)          # blocos de código
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
    # junta parágrafos; colapsa espaços/linhas em branco excessivos
    text = "\n".join(lines)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def parse_story(text: str, *, default_lang: str = "pt", default_narrator: bool = True,
                title: str = "") -> Story:
    """Constrói uma `Story` a partir do conteúdo bruto (front-matter + Markdown)."""
    # normaliza quebras de linha (arquivos de Windows/web usam \r\n): senão o
    # front-matter (fechado por "\n---\n") não casa e vira prosa.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    meta, body = _parse_frontmatter(text)
    lang = meta.get("idioma", meta.get("language", meta.get("lang", default_lang)))
    narrator = _parse_bool(meta.get("narrador", meta.get("narrator", "")),
                           default_narrator)
    ambiance = meta.get("ambientacao", meta.get("ambiance", meta.get("cenario", "seco")))
    ttl = meta.get("titulo", meta.get("title", "")) or title or "historia"
    return Story(title=ttl, prose=strip_markdown(body), lang=lang,
                 narrator=narrator, ambiance=ambiance)


def load_story(path: str | Path, **overrides) -> Story:
    """Lê um arquivo de história (.md/.txt). `overrides`: default_lang/default_narrator."""
    p = Path(path)
    story = parse_story(p.read_text("utf-8"), title=p.stem, **overrides)
    return story
