"""Camada SFX — efeitos sonoros e ambiência como CITAÇÃO de áudio (real ou sintético).

Espelha a camada TTS: um `SfxBackend` agnóstico (contrato), com `LibrarySfxBackend`
(samples reais por tag, o baseline de produção) e `ProceduralSfxBackend` (síntese
determinística, o stand-in runnable). O Orquestrador e o renderer não sabem de qual
fonte veio o som.
"""

from k_nar.sfx.base import SfxBackend, render_all
from k_nar.sfx.library import LibrarySfxBackend
from k_nar.sfx.procedural import ProceduralSfxBackend

__all__ = ["SfxBackend", "LibrarySfxBackend", "ProceduralSfxBackend", "render_all"]
