"""Camada de render (DSP) — consome a Timeline/EDL e produz áudio real.

Depende de numpy (e opcionalmente pedalboard). NÃO é importada pelo core, para
que a lógica de ritmo continue sem dependências.
"""

from k_nar.render.renderer import TimelineRenderer

__all__ = ["TimelineRenderer"]
