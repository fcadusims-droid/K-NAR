"""Base da Camada Director: monta o JSON da cena a partir de decisões por fala.

O que varia entre backends é só o método `_decide` (como classificar cada fala).
Toda a montagem — posição no palco, assembleia do JSON, validação estrita — é
compartilhada aqui, para que regras e LLM produzam exatamente o mesmo contrato.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from k_nar.schema import validate_scene

# Palco: posições estéreo estáveis por ordem de aparição do personagem.
_PAN_SLOTS = [-35, 35, -18, 18, -50, 50, 0]


@runtime_checkable
class Director(Protocol):
    """Qualquer coisa que transforme roteiro -> JSON de cena (PASSAGEM 1)."""

    def direct(self, script: dict[str, Any]) -> dict[str, Any]:
        ...


class BaseDirector:
    """Esqueleto: percorre as falas, chama `_decide` e monta o JSON validado.

    `script` esperado:
        {"cena_id": "...", "ambientacao": "...",
         "falas": [{"personagem": "Alien A", "texto": "..."}, ...]}
    """

    # velocidade de fala por nível de tensão (relativa, nunca segundos)
    _RATE_BY_TENSION = {"baixa": 0.9, "media": 1.0, "alta": 1.08, "extrema": 1.18}

    def direct(self, script: dict[str, Any]) -> dict[str, Any]:
        # PASSAGEM 0 (Screenwriter) entrega `elementos` (narração + diálogo); o formato
        # antigo entrega `falas` (só diálogo). Aceitamos os dois — retrocompatível.
        elementos = script.get("elementos")
        itens = elementos if elementos is not None else \
            script.get("falas", script.get("eventos", []))
        if not itens:
            raise ValueError("script sem 'elementos' nem 'falas'")

        pans: dict[str, int] = {}
        eventos = []
        prev_text = None
        for i, item in enumerate(itens):
            tipo_ev = str(item.get("tipo", "fala")).strip().lower()
            texto = str(item.get("texto", item.get("text", ""))).strip()

            if tipo_ev in ("narracao", "narrador"):
                eventos.append(self._narration_event(item, i, texto))
            else:
                personagem = str(item.get("personagem", item.get("character", "?")))
                if personagem not in pans:
                    pans[personagem] = _PAN_SLOTS[len(pans) % len(_PAN_SLOTS)]
                eventos.append(self._speech_event(item, i, personagem, texto,
                                                  prev_text, pans[personagem]))
            prev_text = texto

        scene = {
            "cena_id": str(script.get("cena_id", "cena")),
            "ambientacao": str(script.get("ambientacao", "seco")),
            "eventos": eventos,
        }
        # gatilhos de ação (sementes de SFX) seguem para a Fase 5; o schema os ignora.
        if script.get("acoes"):
            scene["acoes"] = script["acoes"]
        validate_scene(scene)  # portão estrito: nada sai fora do contrato
        return scene

    # ------------------------------------------------------------------ #
    def _speech_event(self, item, index, personagem, texto, prev_text, pan) -> dict[str, Any]:
        d = self._decide(personagem, texto, index, prev_text, cue=item.get("deixa"))
        tensao = d["tensao"]
        return {
            "id": item.get("id", f"fala_{index+1}"),
            "personagem": personagem,
            "texto": texto,
            "voz": {"tensao": tensao,
                    "velocidade": round(self._RATE_BY_TENSION.get(tensao, 1.0), 2)},
            "entrada": {"tipo": d["tipo"], "agressividade": round(d["agressividade"], 2)},
            "saida": {"pausa": d["pausa"]},
            "palco": {"estereo": pan},
        }

    def _narration_event(self, item, index, texto) -> dict[str, Any]:
        """Narração: mesma leitura de tensão, mas sempre SEQUENCIAL (o narrador não é
        interrompido) e centralizada. A voz do narrador é escolhida no TTS (perfil)."""
        d = self._decide("Narrador", texto, index, None, cue=item.get("deixa"))
        tensao = d["tensao"]
        return {
            "id": item.get("id", f"narr_{index+1}"),
            "tipo_evento": "narracao",
            "personagem": "Narrador",
            "texto": texto,
            "voz": {"tensao": tensao,
                    "velocidade": round(self._RATE_BY_TENSION.get(tensao, 1.0), 2)},
            "entrada": {"tipo": "sequencial", "agressividade": 0.0},
            "saida": {"pausa": d["pausa"]},
            "palco": {"estereo": 0},
        }

    # ------------------------------------------------------------------ #
    def _decide(self, personagem: str, texto: str, index: int,
                prev_text: str | None, cue: str | None = None) -> dict[str, Any]:
        """Devolve {tensao, tipo, agressividade, pausa} para uma fala/narração.
        `cue` é a "deixa" (verbo de fala: gritou/sussurrou) que o Screenwriter extraiu.
        Implementado pelas subclasses (regras ou LLM)."""
        raise NotImplementedError
