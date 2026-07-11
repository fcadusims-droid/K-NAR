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
        falas = script.get("falas", script.get("eventos", []))
        if not falas:
            raise ValueError("script sem 'falas'")

        pans: dict[str, int] = {}
        eventos = []
        prev_text = None
        for i, fala in enumerate(falas):
            personagem = str(fala.get("personagem", fala.get("character", "?")))
            texto = str(fala.get("texto", fala.get("text", ""))).strip()
            if personagem not in pans:
                pans[personagem] = _PAN_SLOTS[len(pans) % len(_PAN_SLOTS)]

            d = self._decide(personagem, texto, i, prev_text)
            tensao = d["tensao"]
            eventos.append({
                "id": fala.get("id", f"fala_{i+1}"),
                "personagem": personagem,
                "texto": texto,
                "voz": {"tensao": tensao,
                        "velocidade": round(self._RATE_BY_TENSION.get(tensao, 1.0), 2)},
                "entrada": {"tipo": d["tipo"], "agressividade": round(d["agressividade"], 2)},
                "saida": {"pausa": d["pausa"]},
                "palco": {"estereo": pans[personagem]},
            })
            prev_text = texto

        scene = {
            "cena_id": str(script.get("cena_id", "cena")),
            "ambientacao": str(script.get("ambientacao", "seco")),
            "eventos": eventos,
        }
        validate_scene(scene)  # portão estrito: nada sai fora do contrato
        return scene

    # ------------------------------------------------------------------ #
    def _decide(self, personagem: str, texto: str, index: int,
                prev_text: str | None) -> dict[str, Any]:
        """Devolve {tensao, tipo, agressividade, pausa} para uma fala.
        Implementado pelas subclasses (regras ou LLM)."""
        raise NotImplementedError
