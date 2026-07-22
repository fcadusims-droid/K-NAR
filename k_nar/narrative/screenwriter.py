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

from k_nar.narrative.lexicons import Lexicon, get_lexicon
from k_nar.text import strip_accents as _norm

_QUOTE_RE = re.compile(r"[“„]([^“”„]+)[”“]|"  # “ ” „
                       r'"([^"]+)"|'                                              # " "
                       r"«([^»]+)»")                               # « »
_WORD_RE = re.compile(r"[0-9A-Za-zÀ-ÿ]+")
_MASK = "\x00%d\x00"
_MASK_RE = re.compile(r"\x00(\d+)\x00")


@runtime_checkable
class Screenwriter(Protocol):
    """Qualquer coisa que transforme prosa -> roteiro estruturado (PASSAGEM 0)."""

    def write(self, prose: str, scene_id: str = "cena", ambiance: str = "seco",
              narrator: bool = True, lang: str = "pt") -> dict[str, Any]:
        ...


class RuleBasedScreenwriter:
    """Segmentação por heurística, dirigida por IDIOMA. Classifica cada frase em:

      * DIÁLOGO   — o que está entre aspas (com locutor + deixa da atribuição);
      * SFX       — som PONTUAL ("passos numa poça"): vira efeito, NÃO é narrado;
      * AMBIÊNCIA — cenário CONTÍNUO ("a floresta", "chovia"): vira cama de fundo;
      * NARRAÇÃO  — o resto da prosa de história (só se `narrator=True`).

    `narrator=False` = modo radiodrama: sem narração, a história vive de vozes + sons.
    A estrutura (aspas, quebra de frases) é agnóstica de idioma; o vocabulário (verbos
    de fala, gatilhos de som) vem do `Lexicon` do idioma (PT/EN/ES). Ver `lexicons.py`.
    """

    # Uma frase é "só som" (vira SFX e NÃO é narrada) se tem gatilho de som pontual,
    # é curta e não menciona um personagem (nome próprio) — é uma didascália sonora.
    _PURE_SFX_MAX_WORDS = 8

    def write(self, prose: str, scene_id: str = "cena", ambiance: str = "seco",
              narrator: bool = True, lang: str = "pt") -> dict[str, Any]:
        lex = get_lexicon(lang)
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
        ambiences: dict[str, str] = {}   # tag -> primeira frase (dedupe: é bed)
        last_speaker: str | None = None
        counter = 0

        for sent in self._sentences(masked):
            ids = _MASK_RE.findall(sent)
            if ids:
                attribution = _MASK_RE.sub(" ", sent)
                speaker, cue = self._attribution(attribution, last_speaker, lex)
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
                continue

            text = sent.strip()
            if not text:
                continue

            amb_tag = self._ambience_trigger(text, lex)
            if amb_tag and amb_tag not in ambiences:
                ambiences[amb_tag] = text  # cama de fundo (dedupe por tag)

            sfx_tag = self._sfx_trigger(text, lex)
            pure_sound = bool(sfx_tag) and self._is_pure_sound_cue(text, lex)
            if sfx_tag:
                counter += 1
                elementos.append({"id": f"sfx_{counter}", "tipo": "sfx",
                                  "tag": sfx_tag, "texto": text})
                acoes.append({"gatilho": sfx_tag, "texto": text, "ancora": f"sfx_{counter}"})

            # Narração: só se há narrador E a frase não é uma didascália sonora pura
            # (som "passos na poça" não deve ser LIDO — vira o efeito, e só).
            if narrator and not pure_sound:
                counter += 1
                elementos.append({"id": f"narr_{counter}", "tipo": "narracao", "texto": text})

        # camas de ambiência primeiro (cobrem a cena inteira; ordem é indiferente)
        beds = [{"id": f"amb_{i+1}", "tipo": "ambiencia", "tag": tag, "texto": src}
                for i, (tag, src) in enumerate(ambiences.items())]

        return {"cena_id": scene_id, "ambientacao": ambiance,
                "elementos": beds + elementos, "acoes": acoes}

    # ------------------------------------------------------------------ #
    @staticmethod
    def _sentences(text: str) -> list[str]:
        """Quebra em frases por [.!?…] + espaço. As aspas já estão mascaradas, então
        a pontuação DENTRO de uma fala não corta a frase errada."""
        parts = re.split(r"(?<=[.!?…])\s+", text.strip())
        return [p for p in parts if p.strip()]

    def _attribution(self, text: str, last_speaker: str | None,
                     lex: Lexicon) -> tuple[str, str | None]:
        """(locutor, deixa) a partir do trecho de atribuição (fora das aspas)."""
        words = _WORD_RE.findall(text)
        cue = next((_norm(w) for w in words if _norm(w) in lex.speech_verbs), None)
        # locutor: última palavra Capitalizada que não é verbo nem stopword
        speaker = None
        for w in words:
            if w[:1].isupper() and _norm(w) not in lex.speech_verbs and _norm(w) not in lex.not_names:
                speaker = w
        return (speaker or last_speaker or "Personagem"), cue

    @staticmethod
    def _sfx_trigger(text: str, lex: Lexicon) -> str | None:
        tags = [lex.sfx_triggers[_norm(w)] for w in _WORD_RE.findall(text)
                if _norm(w) in lex.sfx_triggers]
        if not tags:
            return None
        # preferência pela variante mais específica ("passos" + "poça" -> splash)
        if "passos_poca" in tags:
            return "passos_poca"
        return tags[0]

    @staticmethod
    def _ambience_trigger(text: str, lex: Lexicon) -> str | None:
        for w in _WORD_RE.findall(text):
            tag = lex.ambience_triggers.get(_norm(w))
            if tag:
                return tag
        return None

    def _is_pure_sound_cue(self, text: str, lex: Lexicon) -> bool:
        """Frase que é SÓ um som (didascália): curta e sem nome de personagem."""
        words = _WORD_RE.findall(text)
        if len(words) > self._PURE_SFX_MAX_WORDS:
            return False
        # nome próprio (capitalizado fora do início) => é narração de história, não som puro
        for w in words[1:]:
            if w[:1].isupper() and _norm(w) not in lex.not_names:
                return False
        return True
