"""RuleBasedDirector — decisões por heurística. Sem modelo, sem dependências.

É o baseline honesto: funciona sempre, é determinístico e serve de oráculo para
testar a montagem e de fallback quando o LLM não está disponível ou devolve lixo.
Não é "inteligente" — é uma leitura de pontuação e palavras-gatilho. A camada LLM
(llama.py) substitui só o julgamento semântico, reaproveitando toda a montagem.
"""

from __future__ import annotations

from typing import Any

from k_nar.director.base import BaseDirector

# palavras-gatilho de alta carga dramática (pt-br, sem acento p/ robustez)
_HOT_WORDS = {
    "matar", "morte", "morrer", "sangue", "medo", "nunca", "jamais", "destruir",
    "inevitavel", "guerra", "fogo", "traicao", "fim", "perigo", "corram", "agora",
}

# "Deixas" (verbos de fala) que o Screenwriter extraiu: empurram a tensão.
_LOUD_CUES = {"gritou", "berrou", "exclamou", "bradou", "vociferou", "ordenou", "alertou"}
_SOFT_CUES = {"sussurrou", "murmurou", "cochichou", "gaguejou", "resmungou"}


def _norm(text: str) -> str:
    subs = str.maketrans("áàâãéêíóôõúç", "aaaaeeiooouc")
    return text.lower().translate(subs)


class RuleBasedDirector(BaseDirector):
    def _decide(self, personagem, texto, index, prev_text, cue=None) -> dict[str, Any]:
        low = _norm(texto)
        words = low.split()
        n_words = max(1, len(words))

        # --- tensão: pontuação + palavras-gatilho + caixa alta + deixa ---
        score = 0.0
        score += 0.9 * texto.count("!")
        letters = [c for c in texto if c.isalpha()]
        if letters and sum(c.isupper() for c in letters) / len(letters) > 0.6:
            score += 1.2  # GRITO em maiúsculas
        hits = sum(1 for w in words if w.strip(".,!?") in _HOT_WORDS)
        score += 0.7 * hits
        if texto.endswith("...") or texto.endswith(".."):
            score -= 0.4  # hesitação/suspensão puxa p/ baixo
        # a deixa da narração ("gritou Ana", "sussurrou ele") calibra a atuação
        if cue in _LOUD_CUES:
            score += 1.3
        elif cue in _SOFT_CUES:
            score -= 1.0

        if score >= 2.2:
            tensao = "extrema"
        elif score >= 1.1:
            tensao = "alta"
        elif score >= 0.4:
            tensao = "media"
        else:
            tensao = "baixa"

        # --- entrada: interrupção quando é réplica curta e quente após outra fala ---
        tipo, agg = "sequencial", 0.0
        if index > 0 and prev_text is not None:
            quente = tensao in ("alta", "extrema")
            curta = n_words <= 6
            prev_suspenso = prev_text.rstrip().endswith(("...", "—", "-"))
            if prev_suspenso:
                tipo, agg = "interrupcao", 0.35   # a anterior foi cortada no meio
            elif quente and curta:
                tipo, agg = "interrupcao", 0.25   # réplica ríspida atropela

        # --- pausa de saída ---
        if texto.endswith("..."):
            pausa = "longa"
        elif texto.endswith("?"):
            pausa = "media"
        elif texto.endswith("!"):
            pausa = "curta"
        else:
            pausa = "media" if n_words > 10 else "curta"

        return {"tensao": tensao, "tipo": tipo, "agressividade": agg, "pausa": pausa}
