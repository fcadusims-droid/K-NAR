"""Camada Director (PASSAGEM 1) — transforma roteiro cru em metadados relativos.

Recebe um roteiro simples (personagem + texto por fala) e devolve o JSON da
cena que o Orquestrador consome — classificando tensão, decidindo dinâmica de
entrada (sequencial/interrupção), pausa e posição no palco. Nunca segundos.

Dois backends, mesma interface:
* `RuleBasedDirector` — heurístico, sem dependências, determinístico (baseline).
* `LlamaDirector` — usa um LLM local pequeno (GGUF via llama-cpp) para classificar.

A saída de qualquer um passa por `schema.validate_scene` antes de sair.
"""

from k_nar.director.base import BaseDirector, Director
from k_nar.director.rules import RuleBasedDirector

__all__ = ["BaseDirector", "Director", "RuleBasedDirector"]
