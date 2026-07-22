"""Contrato AGNÓSTICO de efeitos sonoros — o espelho do `TTSBackend` para SOM.

O K-NAR trata SFX/ambiência como CITAÇÃO de áudio real, não como geração neural: o
motor lê a cena, resolve um `tag` ("passos_poca", "floresta_noite") e o backend
devolve o áudio — de uma biblioteca de samples (`LibrarySfxBackend`) ou sintetizado
(`ProceduralSfxBackend`, o stand-in). Trocar a fonte não muda o Orquestrador.

Devolve o MESMO `RenderedClip` do TTS: o que importa é o áudio + a `duration_ms`
REAL medida — é ela que permite ancorar uma fala para reagir ao som (a mesma tese
de duas passagens, agora para efeitos).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from k_nar.tts.base import RenderedClip


@runtime_checkable
class SfxBackend(Protocol):
    """Qualquer objeto que transforme um evento de som (SfxEvent/AmbienceEvent, com
    `.id` e `.tag`) num `RenderedClip`. Tipagem estrutural, sem herança."""

    def render(self, event) -> RenderedClip:
        ...


def render_all(backend: SfxBackend, events: list) -> dict[str, RenderedClip]:
    """Renderiza uma lista de eventos de som -> {event_id: RenderedClip}.

    Espelha `tts.batch.synthesize_all`, mas SFX costuma ser barato (síntese leve ou
    leitura de arquivo), então serial já basta.
    """
    return {ev.id: backend.render(ev) for ev in events}
