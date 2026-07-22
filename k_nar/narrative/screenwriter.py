"""Screenwriter — a PASSAGEM 0: prosa crua → roteiro estruturado.

É o Director "subindo um nível". Antes o pipeline recebia falas já separadas
(personagem + texto); agora recebe a HISTÓRIA em prosa e precisa segmentá-la em
narração, diálogo (com quem fala) e gatilhos de ação (para o SFX da Fase 5).

Mesma filosofia da Camada Director: `RuleBasedScreenwriter` é o baseline honesto —
determinístico, sem modelo, uma leitura de aspas + verbos de fala. Um
`LlamaScreenwriter` (LLM local) faria o julgamento semântico melhor, reaproveitando
o MESMO contrato de saída (o "roteiro estruturado"). O rótulo é do LLM; a montagem e
a validação ficam no código.

Saída (o roteiro estruturado que o `BaseDirector` consome via `elementos`):

    {"cena_id": "...", "ambientacao": "...",
     "elementos": [
        {"tipo": "narracao", "texto": "A porta rangeu."},
        {"tipo": "fala", "personagem": "Ana", "texto": "Quem esta ai?", "deixa": "perguntou"},
        ...],
     "acoes": [{"gatilho": "porta_range", "texto": "A porta rangeu."}]}   # sementes de SFX

Simplificação assumida (documentada, como no RuleBasedDirector): uma frase que
contém aspas é uma linha de DIÁLOGO — o trecho entre aspas vira fala, e o resto da
frase é lido só como ATRIBUIÇÃO (quem fala + verbo), não como narração. Frases sem
aspas viram narração. Prosa real é mais bagunçada; o LLM cobriria os casos difíceis.
"""

from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable

# Verbos de fala (normalizados, sem acento). Servem p/ achar o locutor e a "deixa".
_SPEECH_VERBS = {
    "disse", "falou", "perguntou", "respondeu", "gritou", "berrou", "exclamou",
    "sussurrou", "murmurou", "retrucou", "indagou", "replicou", "ordenou",
    "questionou", "afirmou", "declarou", "avisou", "alertou", "gaguejou",
    "cochichou", "bradou", "vociferou", "resmungou", "pediu", "insistiu",
    "continuou", "concluiu", "acrescentou", "completou", "chamou",
}
# Verbos que carregam tensão (a "deixa" que o Director usa p/ calibrar a atuação).
_LOUD_VERBS = {"gritou", "berrou", "exclamou", "bradou", "vociferou", "ordenou", "alertou"}
_SOFT_VERBS = {"sussurrou", "murmurou", "cochichou", "gaguejou", "resmungou"}

# Palavras capitalizadas que NÃO são nomes de personagem (evita falsos locutores).
_NOT_NAMES = {
    "a", "o", "e", "ele", "ela", "eles", "elas", "entao", "mas", "quando",
    "de", "do", "da", "no", "na", "com", "por", "que", "um", "uma", "os", "as",
    "seu", "sua", "isso", "aquilo", "aquele", "aquela", "depois", "antes",
}

# Gatilhos de ação → tag de SFX (semente da biblioteca da Fase 5). Lexicon pequeno.
_ACTION_TRIGGERS = {
    "rangeu": "porta_range", "range": "porta_range", "rangendo": "porta_range",
    "explodiu": "explosao", "explosao": "explosao", "estourou": "explosao",
    "bateu": "batida", "batida": "batida", "socou": "batida",
    "estilhacou": "vidro_quebra", "quebrou": "vidro_quebra",
    "trovejou": "trovao", "trovao": "trovao", "raio": "trovao",
    "disparou": "tiro", "tiro": "tiro", "atirou": "tiro",
    "passos": "passos", "pisou": "passos", "correu": "passos",
    "vento": "vento", "ventania": "vento", "chuva": "chuva", "sirene": "sirene",
    "motor": "motor", "motores": "motor", "zumbido": "motor", "alarme": "alarme",
}

_QUOTE_RE = re.compile(r"[“„]([^“”„]+)[”“]|"  # “ ” „
                       r'"([^"]+)"|'                                              # " "
                       r"«([^»]+)»")                               # « »
_WORD_RE = re.compile(r"[0-9A-Za-zÀ-ÿ]+")
_MASK = "\x00%d\x00"
_MASK_RE = re.compile(r"\x00(\d+)\x00")


def _norm(text: str) -> str:
    subs = str.maketrans("áàâãéêíóôõúüç", "aaaaeeiooouuc")
    return text.lower().translate(subs)


@runtime_checkable
class Screenwriter(Protocol):
    """Qualquer coisa que transforme prosa -> roteiro estruturado (PASSAGEM 0)."""

    def write(self, prose: str, scene_id: str = "cena",
              ambiance: str = "seco") -> dict[str, Any]:
        ...


class RuleBasedScreenwriter:
    """Segmentação por heurística: aspas → diálogo, resto → narração; verbo de fala
    → locutor + deixa; verbo/substantivo de ação na narração → gatilho de SFX."""

    def write(self, prose: str, scene_id: str = "cena",
              ambiance: str = "seco") -> dict[str, Any]:
        quotes: list[str] = []

        def _mask(m: re.Match) -> str:
            quotes.append(next(g for g in m.groups() if g is not None).strip())
            return _MASK % (len(quotes) - 1)

        masked = _QUOTE_RE.sub(_mask, prose)
        # Quando uma fala é seguida por uma NOVA frase (maiúscula), a pontuação final
        # ficou DENTRO das aspas e o divisor não quebraria ali — a narração seguinte
        # seria engolida como atribuição. Inserimos a fronteira. Mas NÃO quando segue
        # vírgula/dois-pontos ou verbo minúsculo ("perguntou Ana"): isso é atribuição.
        masked = re.sub(r"(\x00\d+\x00)(\s+)([A-ZÀ-Ý\"“«])", r"\1. \3", masked)

        elementos: list[dict[str, Any]] = []
        acoes: list[dict[str, Any]] = []
        last_speaker: str | None = None
        counter = 0

        for sent in self._sentences(masked):
            ids = _MASK_RE.findall(sent)
            if ids:
                attribution = _MASK_RE.sub(" ", sent)
                speaker, cue = self._attribution(attribution, last_speaker)
                last_speaker = speaker
                for qid in ids:
                    counter += 1
                    el: dict[str, Any] = {
                        "id": f"fala_{counter}", "tipo": "fala",
                        "personagem": speaker, "texto": quotes[int(qid)],
                    }
                    if cue:
                        el["deixa"] = cue
                    elementos.append(el)
            else:
                text = sent.strip()
                if not text:
                    continue
                counter += 1
                elementos.append({"id": f"narr_{counter}", "tipo": "narracao", "texto": text})
                trig = self._action_trigger(text)
                if trig:
                    acoes.append({"gatilho": trig, "texto": text, "ancora": f"narr_{counter}"})

        return {"cena_id": scene_id, "ambientacao": ambiance,
                "elementos": elementos, "acoes": acoes}

    # ------------------------------------------------------------------ #
    @staticmethod
    def _sentences(text: str) -> list[str]:
        """Quebra em frases por [.!?…] + espaço. As aspas já estão mascaradas, então
        a pontuação DENTRO de uma fala não corta a frase errada."""
        parts = re.split(r"(?<=[.!?…])\s+", text.strip())
        return [p for p in parts if p.strip()]

    def _attribution(self, text: str, last_speaker: str | None) -> tuple[str, str | None]:
        """(locutor, deixa) a partir do trecho de atribuição (fora das aspas)."""
        words = _WORD_RE.findall(text)
        cue = next((_norm(w) for w in words if _norm(w) in _SPEECH_VERBS), None)
        # locutor: última palavra Capitalizada que não é verbo nem stopword
        speaker = None
        for w in words:
            if w[:1].isupper() and _norm(w) not in _SPEECH_VERBS and _norm(w) not in _NOT_NAMES:
                speaker = w
        return (speaker or last_speaker or "Personagem"), cue

    @staticmethod
    def _action_trigger(text: str) -> str | None:
        for w in _WORD_RE.findall(text):
            tag = _ACTION_TRIGGERS.get(_norm(w))
            if tag:
                return tag
        return None
