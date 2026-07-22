"""Léxicos por IDIOMA para o Screenwriter (verbos de fala, gatilhos de som).

A segmentação estrutural (aspas → diálogo, quebra de frases) é agnóstica de idioma;
o que MUDA por idioma é o vocabulário: os verbos de fala que revelam o locutor e a
deixa, e as palavras que disparam SFX/ambiência. Cada idioma traz um `Lexicon`; as
CHAVES já vêm normalizadas (sem acento, minúsculas) porque o lookup usa `strip_accents`.

As TAGS de som são compartilhadas entre idiomas (o mesmo `tiro`/`floresta_noite` da
biblioteca), então só o gatilho (a palavra) muda — "tiro"/"shot"/"disparo" → `tiro`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Lexicon:
    speech_verbs: frozenset[str]
    loud_verbs: frozenset[str]
    soft_verbs: frozenset[str]
    not_names: frozenset[str]
    sfx_triggers: dict[str, str] = field(default_factory=dict)
    ambience_triggers: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
#  Português                                                                   #
# --------------------------------------------------------------------------- #
PT = Lexicon(
    speech_verbs=frozenset({
        "disse", "falou", "perguntou", "respondeu", "gritou", "berrou", "exclamou",
        "sussurrou", "murmurou", "retrucou", "indagou", "replicou", "ordenou",
        "questionou", "afirmou", "declarou", "avisou", "alertou", "gaguejou",
        "cochichou", "bradou", "vociferou", "resmungou", "pediu", "insistiu",
        "continuou", "concluiu", "acrescentou", "completou", "chamou",
    }),
    loud_verbs=frozenset({"gritou", "berrou", "exclamou", "bradou", "vociferou", "ordenou", "alertou"}),
    soft_verbs=frozenset({"sussurrou", "murmurou", "cochichou", "gaguejou", "resmungou"}),
    not_names=frozenset({
        "a", "o", "e", "ele", "ela", "eles", "elas", "entao", "mas", "quando",
        "de", "do", "da", "no", "na", "com", "por", "que", "um", "uma", "os", "as",
        "seu", "sua", "isso", "aquilo", "aquele", "aquela", "depois", "antes",
    }),
    sfx_triggers={
        "rangeu": "porta_range", "range": "porta_range", "rangendo": "porta_range",
        "explodiu": "explosao", "explosao": "explosao", "estourou": "explosao",
        "bateu": "batida", "batida": "batida", "socou": "batida",
        "estilhacou": "vidro_quebra", "quebrou": "vidro_quebra",
        "trovejou": "trovao", "trovao": "trovao", "raio": "trovao",
        "disparou": "tiro", "tiro": "tiro", "tiros": "tiro", "atirou": "tiro",
        "passos": "passos", "pisou": "passos", "poca": "passos_poca", "poça": "passos_poca",
        "sirene": "sirene", "alarme": "alarme",
    },
    ambience_triggers={
        "floresta": "floresta_noite", "mata": "floresta_noite", "selva": "floresta_noite",
        "chuva": "chuva", "chovia": "chuva", "chovendo": "chuva", "temporal": "chuva",
        "vento": "vento", "ventania": "vento", "brisa": "vento",
        "motor": "motor", "motores": "motor", "zumbido": "motor", "nave": "motor",
        "cidade": "cidade", "multidao": "multidao", "praca": "multidao",
    },
)

# --------------------------------------------------------------------------- #
#  English                                                                     #
# --------------------------------------------------------------------------- #
EN = Lexicon(
    speech_verbs=frozenset({
        "said", "asked", "replied", "answered", "shouted", "yelled", "screamed",
        "whispered", "muttered", "murmured", "exclaimed", "cried", "called",
        "continued", "added", "declared", "warned", "ordered", "stammered",
        "snapped", "hissed", "growled", "begged", "insisted", "roared", "bellowed",
    }),
    loud_verbs=frozenset({"shouted", "yelled", "screamed", "exclaimed", "bellowed", "roared", "ordered"}),
    soft_verbs=frozenset({"whispered", "muttered", "murmured", "mumbled", "stammered"}),
    not_names=frozenset({
        "the", "a", "an", "he", "she", "they", "it", "then", "but", "when", "and",
        "of", "to", "with", "for", "his", "her", "their", "this", "that", "after",
        "before", "so", "as", "at", "in", "on",
    }),
    sfx_triggers={
        "creaked": "porta_range", "creak": "porta_range", "creaking": "porta_range",
        "exploded": "explosao", "explosion": "explosao", "blast": "explosao",
        "banged": "batida", "bang": "batida", "knock": "batida", "knocked": "batida",
        "shattered": "vidro_quebra", "smashed": "vidro_quebra", "broke": "vidro_quebra",
        "thunder": "trovao", "thundered": "trovao", "lightning": "trovao",
        "gunshot": "tiro", "shot": "tiro", "fired": "tiro", "gunfire": "tiro",
        "footsteps": "passos", "steps": "passos", "puddle": "passos_poca",
        "siren": "sirene", "alarm": "alarme",
    },
    ambience_triggers={
        "forest": "floresta_noite", "woods": "floresta_noite", "jungle": "floresta_noite",
        "rain": "chuva", "raining": "chuva", "storm": "chuva",
        "wind": "vento", "breeze": "vento", "gale": "vento",
        "engine": "motor", "engines": "motor", "hum": "motor", "ship": "motor",
        "city": "cidade", "crowd": "multidao", "ocean": "oceano", "waves": "oceano", "sea": "oceano",
    },
)

# --------------------------------------------------------------------------- #
#  Español                                                                     #
# --------------------------------------------------------------------------- #
ES = Lexicon(
    speech_verbs=frozenset({
        "dijo", "pregunto", "respondio", "grito", "susurro", "murmuro", "exclamo",
        "contesto", "replico", "ordeno", "afirmo", "declaro", "aviso", "advirtio",
        "balbuceo", "farfullo", "bramo", "rugio", "pidio", "insistio", "continuo",
        "anadio", "llamo", "chillo",
    }),
    loud_verbs=frozenset({"grito", "chillo", "exclamo", "bramo", "rugio", "ordeno", "advirtio"}),
    soft_verbs=frozenset({"susurro", "murmuro", "farfullo", "balbuceo"}),
    not_names=frozenset({
        "el", "la", "los", "las", "un", "una", "y", "pero", "cuando", "de", "con",
        "entonces", "que", "su", "sus", "esto", "eso", "aquel", "aquella", "despues",
        "antes", "en", "por", "para",
    }),
    sfx_triggers={
        "crujio": "porta_range", "crujido": "porta_range",
        "exploto": "explosao", "explosion": "explosao", "estallo": "explosao",
        "golpeo": "batida", "golpe": "batida", "toco": "batida",
        "rompio": "vidro_quebra", "estallido": "vidro_quebra",
        "trueno": "trovao", "rayo": "trovao", "relampago": "trovao",
        "disparo": "tiro", "tiro": "tiro", "disparos": "tiro",
        "pasos": "passos", "charco": "passos_poca",
        "sirena": "sirene", "alarma": "alarme",
    },
    ambience_triggers={
        "bosque": "floresta_noite", "selva": "floresta_noite",
        "lluvia": "chuva", "llovia": "chuva", "tormenta": "chuva",
        "viento": "vento", "brisa": "vento",
        "motor": "motor", "motores": "motor", "zumbido": "motor", "nave": "motor",
        "ciudad": "cidade", "multitud": "multidao", "mar": "oceano", "olas": "oceano",
    },
)

LEXICONS: dict[str, Lexicon] = {
    "pt": PT, "pt_br": PT, "pt-br": PT, "portugues": PT,
    "en": EN, "en_us": EN, "en-us": EN, "english": EN, "ingles": EN,
    "es": ES, "es_es": ES, "es-es": ES, "espanol": ES, "spanish": ES,
}


def get_lexicon(lang: str) -> Lexicon:
    """Léxico do idioma (default PT). Aceita 'pt', 'en_US', 'espanol'..."""
    return LEXICONS.get(str(lang).strip().lower().replace(" ", ""), PT)
