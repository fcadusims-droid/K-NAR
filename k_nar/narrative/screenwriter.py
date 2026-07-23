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
    # Máximo de camas de ambiência simultâneas (evita empilhar beds incoerentes).
    _MAX_AMBIENCES = 3

    def write(self, prose: str, scene_id: str = "cena", ambiance: str = "seco",
              narrator: bool = True, lang: str = "pt") -> dict[str, Any]:
        lex = get_lexicon(lang)
        # Diálogo por TRAVESSÃO (— Fala — disse Fulano) é o padrão literário em PT/ES;
        # convertemos para aspas para reusar toda a maquinaria de atribuição.
        prose = self._travessoes_para_aspas(prose, lex)
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
            if amb_tag:
                # conta frequência: uma cama é a atmosfera PERSISTENTE, não uma menção
                # de passagem. No fim, mantemos só as mais recorrentes (evita empilhar
                # ambiências incoerentes de uma palavra solta: "tempestade formando longe").
                c, _ = ambiences.get(amb_tag, (0, text))
                ambiences[amb_tag] = (c + 1, text)

            sfx_tag = self._sfx_trigger(text, lex)
            pure_sound = bool(sfx_tag) and self._is_pure_sound_cue(text, lex)
            if sfx_tag:
                counter += 1
                el = {"id": f"sfx_{counter}", "tipo": "sfx", "tag": sfx_tag, "texto": text}
                dist = self._distance_of(text, lex)   # "ao longe" -> som distante
                if dist != "media":
                    el["distancia"] = dist
                elementos.append(el)
                acoes.append({"gatilho": sfx_tag, "texto": text, "ancora": f"sfx_{counter}"})

            # Narração: só se há narrador E a frase não é uma didascália sonora pura
            # (som "passos na poça" não deve ser LIDO — vira o efeito, e só).
            if narrator and not pure_sound:
                counter += 1
                elementos.append({"id": f"narr_{counter}", "tipo": "narracao", "texto": text})

        # camas de ambiência: mantém só as MAIS_AMBIENCES mais frequentes (a atmosfera
        # dominante), evitando um empilhamento incoerente de beds soltos.
        top = sorted(ambiences.items(), key=lambda kv: (-kv[1][0], kv[0]))[: self._MAX_AMBIENCES]
        beds = [{"id": f"amb_{i+1}", "tipo": "ambiencia", "tag": tag, "texto": src}
                for i, (tag, (_c, src)) in enumerate(top)]

        # Espaço acústico: se o autor não fixou a ambiência (default "seco"), detecta
        # o lugar na prosa ("galpão vazio" → eco de galpão na voz de todos).
        final_ambiance = ambiance
        if not ambiance or ambiance == "seco":
            final_ambiance = self._detect_space(prose, lex) or ambiance

        return {"cena_id": scene_id, "ambientacao": final_ambiance,
                "elementos": beds + elementos, "acoes": acoes}

    @staticmethod
    def _detect_space(prose: str, lex: Lexicon) -> str | None:
        """Preset de reverb do ESPAÇO dominante na prosa (galpão/catedral/caverna...)."""
        if not lex.space_triggers:
            return None
        counts: dict[str, int] = {}
        for w in _WORD_RE.findall(prose):
            preset = lex.space_triggers.get(_norm(w))
            if preset:
                counts[preset] = counts.get(preset, 0) + 1
        return max(counts, key=counts.get) if counts else None

    # ------------------------------------------------------------------ #
    def _travessoes_para_aspas(self, prose: str, lex: Lexicon) -> str:
        """Converte linhas de diálogo por travessão em aspas.

            — Quieto hoje — comenta Baiano, ao lado dele.
              -> "Quieto hoje", comenta Baiano, ao lado dele.
            — Não sei. — respondeu ela. — É o trabalho.
              -> "Não sei. É o trabalho.", respondeu ela.

        A fala é o(s) segmento(s) sem verbo de fala; o segmento com verbo é a
        atribuição, que sai FORA das aspas (o parser de atribuição a lê depois)."""
        out = []
        for line in prose.split("\n"):
            s = line.strip()
            if s[:1] not in ("—", "–"):        # só travessão (não hífen -, que é lista/palavra)
                out.append(line)
                continue
            inner = s.lstrip("—–").strip()
            segs = [seg.strip() for seg in re.split(r"\s*[—–]\s*", inner) if seg.strip()]
            fala, atrib = [], []
            for i, seg in enumerate(segs):
                words = _WORD_RE.findall(seg)
                # atribuição: segmento (após o 1º) cujo verbo de fala aparece no
                # INÍCIO ("comenta Baiano...", "responde Renê..."). Robusto a atribuições
                # longas — o que importa é o verbo vir cedo, não o tamanho.
                if i > 0 and any(_norm(w) in lex.speech_verbs for w in words[:3]):
                    atrib.append(seg)
                else:
                    fala.append(seg)
            if not fala:
                out.append(line)
                continue
            quoted = '"' + " ".join(fala) + '"'
            if atrib:
                quoted += ", " + " ".join(atrib)
                if quoted[-1] not in ".!?":
                    quoted += "."
            out.append(quoted)
        return "\n".join(out)

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
    def _distance_of(text: str, lex: Lexicon) -> str:
        """Distância do som na frase: 'ao longe' → longe, 'à queima-roupa' → perto."""
        words = {_norm(w) for w in _WORD_RE.findall(text)}
        if "queima" in words and "roupa" in words:      # à queima-roupa
            return "perto"
        if words & lex.far_words:
            if words & {"horizonte", "lonjura", "horizon"}:
                return "muito_longe"                     # bem no fim do horizonte
            return "longe"
        if words & lex.near_words:
            return "perto"
        return "media"

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
