"""LlamaDirector — o Diretor de Palco com um LLM local pequeno (GGUF via llama-cpp).

Mantém o trabalho do modelo MÍNIMO e tratável (a "alternativa viável" da conversa):
para cada fala ele só classifica tensão + tipo de entrada + pausa, devolvendo um
JSON curto. Toda a montagem/validação continua na base. Se o modelo devolver algo
fora do contrato (comum em modelos pequenos), caímos no julgamento das regras para
aquele campo — nunca um fallback silencioso que mascara erro: o campo inválido é
substituído por uma decisão determinística e auditável.

Requer o extra [llm]:  pip install llama-cpp-python  + um modelo .gguf local.
"""

from __future__ import annotations

import json
import re
from typing import Any

from k_nar.director.base import BaseDirector
from k_nar.director.rules import RuleBasedDirector

_TENSOES = {"baixa", "media", "alta", "extrema"}
_TIPOS = {"sequencial", "interrupcao", "sobreposicao"}
_PAUSAS = {"nenhuma", "curta", "media", "longa"}

_SYSTEM = (
    "Voce e um diretor de audio drama. Para a fala dada, classifique a performance. "
    "Responda APENAS um JSON valido, sem texto extra, no formato:\n"
    '{"tensao":"baixa|media|alta|extrema","tipo":"sequencial|interrupcao|sobreposicao",'
    '"agressividade":0.0,"pausa":"nenhuma|curta|media|longa"}\n'
    "tensao = carga emocional. tipo = como a fala entra em relacao a anterior "
    "(interrupcao = atropela a anterior). agressividade (0..1) so importa em "
    "interrupcao/sobreposicao. pausa = silencio dramatico depois da fala."
)


class LlamaDirector(BaseDirector):
    def __init__(self, model_path: str, n_ctx: int = 2048, n_threads: int = 4,
                 temperature: float = 0.2, verbose: bool = False):
        from llama_cpp import Llama  # import tardio: só quando o LLM é usado
        self.llm = Llama(model_path=model_path, n_ctx=n_ctx, n_threads=n_threads,
                         verbose=verbose)
        self.temperature = temperature
        self._fallback = RuleBasedDirector()

    # ------------------------------------------------------------------ #
    def _decide(self, personagem, texto, index, prev_text) -> dict[str, Any]:
        base = self._fallback._decide(personagem, texto, index, prev_text)  # rede de seguranca
        raw = self._ask(texto, prev_text, index)
        parsed = _extract_json(raw)
        if not parsed:
            return base

        # cada campo e validado contra o contrato; invalido -> valor das regras.
        out = dict(base)
        if parsed.get("tensao") in _TENSOES:
            out["tensao"] = parsed["tensao"]
        if parsed.get("tipo") in _TIPOS and index > 0:
            out["tipo"] = parsed["tipo"]
        if parsed.get("pausa") in _PAUSAS:
            out["pausa"] = parsed["pausa"]
        try:
            agg = float(parsed.get("agressividade"))
            if 0.0 <= agg <= 1.0:
                out["agressividade"] = agg
        except (TypeError, ValueError):
            pass
        # coerência: agressividade só faz sentido em interrupção/sobreposição
        if out["tipo"] == "sequencial":
            out["agressividade"] = 0.0
        return out

    def _ask(self, texto: str, prev_text: str | None, index: int) -> str:
        ctx = f"Fala anterior: \"{prev_text}\"\n" if index > 0 and prev_text else ""
        user = f"{ctx}Fala atual: \"{texto}\""
        out = self.llm.create_chat_completion(
            messages=[{"role": "system", "content": _SYSTEM},
                      {"role": "user", "content": user}],
            max_tokens=80, temperature=self.temperature,
        )
        return out["choices"][0]["message"]["content"]


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extrai o primeiro objeto {...} do texto do modelo, tolerante a ruído."""
    m = re.search(r"\{.*?\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None
