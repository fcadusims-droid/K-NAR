"""Casting — escolhe a VOZ de cada personagem pela sua descrição na história.

O usuário não quer "voz de homem" e "voz de mulher" e pronto: quer que o K-NAR leia
a APARÊNCIA e a IDADE do personagem no texto ("um velho grisalho de voz rouca", "a
menina") e escolha uma voz coerente — idade, gênero, timbre. Este módulo faz a
inferência de traços e o mapeamento traço → ajuste de voz.

Como funciona (e os limites honestos):

* Os traços saem de DESCRITORES explícitos na prosa perto do nome do personagem
  ("velho", "menina", "rouca") — NÃO do nome em si. Adivinhar gênero pelo nome
  erra e "misgenera" personagens reais; sem descritor, o padrão é uma voz neutra.
* Com os modelos de voz que existem hoje (poucos por idioma), a diferenciação é
  feita por PITCH e RITMO sobre o modelo base (como a `ProsodyPolicy` já faz por
  personagem). A estrutura aceita mapear traço → modelo Piper real (voz/sotaque
  distintos) assim que mais vozes forem baixadas — aí é só preencher os candidatos.

Saída: um `dict[personagem -> VoiceProfile]` pronto para o `MultiVoiceTTSBackend`.
Stdlib puro (o mapeamento é dado; o TTS é que gera som).
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass

from k_nar.text import strip_accents as _norm
from k_nar.tts.multivoice import VoiceProfile

_WORD = re.compile(r"[0-9A-Za-zÀ-ÿ]+")


@dataclass(frozen=True)
class Traits:
    """Traços de voz inferidos de um personagem."""

    gender: str = "?"        # "m" | "f" | "?" (desconhecido → voz neutra)
    age: str = "adulto"      # "crianca" | "jovem" | "adulto" | "idoso"
    register: str = "neutro"  # "grave" | "agudo" | "neutro"


# --------------------------------------------------------------------------- #
#  Vocabulário de descritores por idioma (chaves já normalizadas: sem acento). #
#  Um mesmo termo pode votar em duas dimensões (ex.: "menino" = masculino +    #
#  criança) — é o esperado.                                                    #
# --------------------------------------------------------------------------- #
_TRAITS = {
    "pt": {
        "male": {"homem", "rapaz", "garoto", "menino", "senhor", "moco", "cara",
                 "sujeito", "pai", "avo", "tio", "irmao", "rei", "soldado", "velho",
                 "rapazote", "guri", "principe", "cavalheiro", "patrao"},
        "female": {"mulher", "moca", "garota", "menina", "senhora", "dama", "mae",
                   "tia", "irma", "rainha", "velha", "mocinha", "princesa", "patroa",
                   "menininha", "dona", "vovo", "vovó"},
        "child": {"crianca", "menino", "menina", "garoto", "garota", "bebe",
                  "guri", "menininha", "menininho", "garotinho", "garotinha"},
        "young": {"jovem", "rapaz", "moco", "moca", "adolescente", "mocinha", "rapazote"},
        "old": {"velho", "velha", "idoso", "idosa", "anciao", "ancia", "grisalho",
                "grisalha", "encanecido", "vovo", "vovó", "senil"},
        "grave": {"grave", "rouca", "rouco", "cavernosa", "cavernoso", "profunda",
                  "profundo", "trovejante", "baritono", "grossa", "grosso", "ronco"},
        "agudo": {"fina", "fino", "aguda", "agudo", "esganicada", "esganicado",
                  "estridente", "suave", "docil"},
    },
    "en": {
        "male": {"man", "boy", "guy", "gentleman", "sir", "lord", "father", "uncle",
                 "king", "husband", "brother", "old", "fellow", "lad", "prince", "master"},
        "female": {"woman", "girl", "lady", "madam", "mother", "aunt", "queen", "wife",
                   "sister", "maiden", "lass", "princess", "mistress", "dame"},
        "child": {"child", "boy", "girl", "kid", "baby", "toddler", "little", "youngster"},
        "young": {"young", "teenager", "teen", "youth", "lad", "lass", "adolescent"},
        "old": {"old", "elderly", "aged", "ancient", "grey", "gray", "grizzled",
                "wrinkled", "senile"},
        "grave": {"deep", "gravelly", "gruff", "booming", "baritone", "hoarse",
                  "raspy", "low"},
        "agudo": {"high", "shrill", "thin", "squeaky", "soft", "reedy"},
    },
    "es": {
        "male": {"hombre", "chico", "muchacho", "nino", "senor", "viejo", "padre",
                 "tio", "rey", "hermano", "mozo", "principe", "caballero", "amo"},
        "female": {"mujer", "chica", "muchacha", "nina", "senora", "vieja", "madre",
                   "tia", "reina", "hermana", "dama", "princesa", "ama", "doncella"},
        "child": {"nino", "nina", "chico", "chica", "bebe", "pequeno", "pequena",
                  "chiquillo", "chiquilla"},
        "young": {"joven", "adolescente", "muchacho", "muchacha", "mozo", "moza"},
        "old": {"viejo", "vieja", "anciano", "anciana", "canoso", "canosa", "senil"},
        "grave": {"grave", "ronca", "ronco", "profunda", "profundo", "atronadora",
                  "cavernosa", "grueso", "gruesa"},
        "agudo": {"aguda", "agudo", "fina", "fino", "chillona", "chillon", "suave"},
    },
}


def _lang_key(lang: str) -> str:
    k = str(lang or "pt").strip().lower().replace(" ", "")
    for pref in ("pt", "en", "es"):
        if k.startswith(pref):
            return pref
    return "pt"


# --------------------------------------------------------------------------- #
#  Traço → ajuste de voz (pitch em semitons, ritmo em multiplicador).         #
#  Grave/agudo por idade+gênero; o registro (rouca/fina) soma por cima.       #
# --------------------------------------------------------------------------- #
_BASE = {
    ("m", "crianca"): (5.0, 1.05), ("f", "crianca"): (5.5, 1.06), ("?", "crianca"): (5.0, 1.05),
    ("m", "jovem"):   (1.0, 1.00), ("f", "jovem"):   (3.5, 1.02), ("?", "jovem"):   (2.0, 1.01),
    ("m", "adulto"):  (-1.5, 0.98), ("f", "adulto"): (2.5, 1.00), ("?", "adulto"):  (0.0, 1.00),
    ("m", "idoso"):   (-4.0, 0.90), ("f", "idoso"):  (0.5, 0.93), ("?", "idoso"):   (-2.0, 0.92),
}
_REGISTER = {"grave": -2.5, "agudo": 2.5, "neutro": 0.0}
_PITCH_CLAMP = 7.5


def infer_traits(characters, prose: str, lang: str = "pt") -> dict[str, Traits]:
    """Infere `Traits` de cada personagem varrendo a prosa. Uma frase que menciona UM
    único personagem conhecido credita seus descritores a ele (evita cross-atribuição
    quando dois personagens dividem a frase)."""
    key = _lang_key(lang)
    tw = _TRAITS[key]
    chars = [c for c in characters
             if c and c not in ("Narrador", "?", "Personagem", "__EU__")]
    norm_names = {c: _norm(c) for c in chars}
    votes = {c: {"male": 0, "female": 0, "child": 0, "young": 0, "old": 0,
                 "grave": 0, "agudo": 0} for c in chars}

    for sent in re.split(r"(?<=[.!?…])\s+", prose):
        words = [_norm(w) for w in _WORD.findall(sent)]
        wset = set(words)
        present = [c for c in chars if norm_names[c] in wset]
        if len(present) != 1:
            continue  # nenhum ou ambíguo: não credita
        c = present[0]
        for dim, vocab in tw.items():
            if wset & vocab:
                votes[c][dim] += 1

    out: dict[str, Traits] = {}
    for c in chars:
        v = votes[c]
        gender = "m" if v["male"] > v["female"] else "f" if v["female"] > v["male"] else "?"
        if v["child"]:
            age = "crianca"
        elif v["old"]:
            age = "idoso"
        elif v["young"]:
            age = "jovem"
        else:
            age = "adulto"
        register = "grave" if v["grave"] > v["agudo"] else "agudo" if v["agudo"] > v["grave"] else "neutro"
        out[c] = Traits(gender=gender, age=age, register=register)
    return out


def _jitter(name: str) -> float:
    """Deslocamento determinístico e pequeno por nome (semitons), p/ dois personagens
    do MESMO arquétipo não soarem idênticos. Estável entre processos (crc32)."""
    h = zlib.crc32(name.encode("utf-8"))
    return ((h % 1000) / 1000.0 - 0.5) * 3.0  # ~[-1.5, +1.5]


def voice_for(traits: Traits, name: str = "") -> VoiceProfile:
    """Traços → `VoiceProfile` (pitch/ritmo sobre o modelo base). O modelo real fica
    None (voz base do idioma); a estrutura aceita um modelo por gênero quando houver."""
    pitch, rate = _BASE.get((traits.gender, traits.age), _BASE[("?", "adulto")])
    pitch += _REGISTER.get(traits.register, 0.0) + _jitter(name)
    pitch = max(-_PITCH_CLAMP, min(_PITCH_CLAMP, pitch))
    return VoiceProfile(model_path=None, pitch_shift=round(pitch, 2), rate=round(rate, 3))


def cast_voices(characters, prose: str, lang: str = "pt") -> dict[str, VoiceProfile]:
    """Elenca a história inteira: `dict[personagem -> VoiceProfile]`. O narrador NÃO é
    elencado aqui (tem voz própria no pipeline). Personagens sem descritor caem numa
    voz adulta neutra (só com o jitter que os diferencia)."""
    traits = infer_traits(characters, prose, lang)
    return {c: voice_for(t, name=c) for c, t in traits.items()}
