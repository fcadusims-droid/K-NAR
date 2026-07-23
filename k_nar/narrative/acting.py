"""Inferência de ATUAÇÃO — decide a EMOÇÃO (e intensidade) de cada fala/narração.

É a "leitura de cena" que faltava: em vez de tudo sair neutro, cada linha ganha uma
intenção emocional a partir de sinais objetivos — pontuação, palavras de emoção, o
verbo de fala (a deixa), o CLIMA da cena (um termômetro que sobe no suspense) e a
REAÇÃO à linha anterior (contágio). A `EmotionPolicy` depois traduz isso em voz.

Baseline honesto por regras (determinístico, sem modelo). O `LlamaDirector` faz o
mesmo julgamento com um LLM, reaproveitando o MESMO contrato (emoção + intensidade).
Stdlib puro.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from k_nar.emotion import EmotionPolicy
from k_nar.text import strip_accents as _norm

_WORD = re.compile(r"[0-9A-Za-zÀ-ÿ]+")

# --------------------------------------------------------------------------- #
#  Palavras de emoção por idioma (chave normalizada → emoção).                #
# --------------------------------------------------------------------------- #
_EMO_WORDS = {
    "pt": {
        # medo
        "medo": "medo", "assustado": "medo", "assustada": "medo", "apavorado": "medo",
        "pavor": "medo", "tremia": "medo", "tremendo": "medo", "gelou": "medo",
        "arrepio": "medo", "aterrorizado": "medo", "susto": "medo", "temor": "medo",
        # raiva
        "raiva": "raiva", "odio": "raiva", "furioso": "raiva", "furiosa": "raiva",
        "maldito": "raiva", "maldita": "raiva", "droga": "raiva", "diabo": "raiva",
        "cala": "raiva", "merda": "raiva", "irritado": "raiva", "bravo": "raiva",
        "inferno": "raiva", "desgraca": "raiva",
        # tristeza
        "triste": "tristeza", "chorou": "tristeza", "chorando": "tristeza",
        "lagrima": "tristeza", "lagrimas": "tristeza", "sozinho": "tristeza",
        "saudade": "tristeza", "luto": "tristeza", "desespero": "tristeza",
        # alegria
        "feliz": "alegria", "alegre": "alegria", "riu": "alegria", "rindo": "alegria",
        "otimo": "alegria", "adorei": "alegria", "maravilha": "alegria",
        "sorriu": "alegria", "sorrindo": "alegria",
        # suspense
        "silencio": "suspense", "quieto": "suspense", "imovel": "suspense",
        "estranho": "suspense", "errado": "suspense", "sombra": "suspense",
        "parado": "suspense",
        # urgencia
        "corre": "urgencia", "corram": "urgencia", "depressa": "urgencia",
        "socorro": "urgencia", "cuidado": "urgencia", "rapido": "urgencia",
        # cansaco
        "cansado": "cansaco", "cansada": "cansaco", "exausto": "cansaco",
        "suspirou": "cansaco", "suspiro": "cansaco",
        # alivio / surpresa / ternura / suplica
        "enfim": "alivio", "finalmente": "alivio", "ufa": "alivio", "aliviado": "alivio",
        "impossivel": "surpresa", "inacreditavel": "surpresa", "serio": "surpresa",
        "caramba": "surpresa", "nossa": "surpresa",
        "querido": "ternura", "querida": "ternura", "calma": "ternura", "amor": "ternura",
        "imploro": "suplica", "suplico": "suplica", "favor": "suplica",
    },
    "en": {
        "fear": "medo", "afraid": "medo", "terrified": "medo", "trembling": "medo",
        "scared": "medo", "dread": "medo",
        "anger": "raiva", "hate": "raiva", "furious": "raiva", "damn": "raiva",
        "shut": "raiva", "hell": "raiva", "angry": "raiva",
        "sad": "tristeza", "cried": "tristeza", "crying": "tristeza", "tears": "tristeza",
        "alone": "tristeza", "grief": "tristeza",
        "happy": "alegria", "glad": "alegria", "laughed": "alegria", "smiled": "alegria",
        "wonderful": "alegria",
        "silence": "suspense", "quiet": "suspense", "still": "suspense",
        "strange": "suspense", "wrong": "suspense", "shadow": "suspense",
        "run": "urgencia", "hurry": "urgencia", "help": "urgencia", "quick": "urgencia",
        "careful": "urgencia",
        "tired": "cansaco", "exhausted": "cansaco", "sighed": "cansaco",
        "finally": "alivio", "relieved": "alivio",
        "impossible": "surpresa", "unbelievable": "surpresa",
        "dear": "ternura", "love": "ternura", "please": "suplica", "beg": "suplica",
    },
    "es": {
        "miedo": "medo", "asustado": "medo", "aterrorizado": "medo", "temblaba": "medo",
        "pavor": "medo",
        "ira": "raiva", "odio": "raiva", "furioso": "raiva", "maldito": "raiva",
        "calla": "raiva", "infierno": "raiva",
        "triste": "tristeza", "lloro": "tristeza", "llorando": "tristeza",
        "lagrimas": "tristeza", "solo": "tristeza",
        "feliz": "alegria", "rio": "alegria", "sonrio": "alegria",
        "silencio": "suspense", "quieto": "suspense", "extrano": "suspense",
        "sombra": "suspense",
        "corre": "urgencia", "rapido": "urgencia", "ayuda": "urgencia", "cuidado": "urgencia",
        "cansado": "cansaco", "agotado": "cansaco", "suspiro": "cansaco",
        "por fin": "alivio", "finalmente": "alivio",
        "imposible": "surpresa", "increible": "surpresa",
        "querido": "ternura", "amor": "ternura", "favor": "suplica", "suplico": "suplica",
    },
}

# verbo de fala (a "deixa") → emoção. União leve entre idiomas (chaves normalizadas).
_CUE_EMOTION = {
    "gritou": "raiva", "berrou": "raiva", "bradou": "raiva", "vociferou": "raiva",
    "grita": "raiva", "berra": "raiva", "shouted": "raiva", "yelled": "raiva",
    "screamed": "medo", "grito": "raiva",
    "sussurrou": "suspense", "murmurou": "suspense", "cochichou": "suspense",
    "whispered": "suspense", "muttered": "cansaco", "murmured": "suspense",
    "sussurra": "suspense", "murmura": "suspense", "susurro": "suspense",
    "resmungou": "cansaco", "resmunga": "cansaco", "grumbled": "cansaco",
    "implorou": "suplica", "begged": "suplica", "suplico": "suplica",
    "ordenou": "ordem", "ordered": "ordem", "ordena": "ordem", "ordeno": "ordem",
    "exclamou": "surpresa", "exclaimed": "surpresa", "exclamo": "surpresa",
    "chorou": "tristeza", "cried": "tristeza",
}


@dataclass(frozen=True)
class Persona:
    """Temperamento de um personagem: enviesa a emoção e a intensidade da atuação.

    `intensity_scale` >1 = mais expressivo (o novato nervoso); <1 = mais contido (o
    veterano calmo). `bias`/`bias_weight` puxam para uma emoção-base (ex.: o nervoso
    tende ao medo; o cansado, ao cansaço)."""

    intensity_scale: float = 1.0
    bias: str = ""
    bias_weight: float = 0.0


# descritores de temperamento na prosa → Persona (varre perto do nome, como o casting).
_TEMPERAMENT = {
    "nervoso": Persona(1.25, "medo", 0.6), "nervosa": Persona(1.25, "medo", 0.6),
    "ansioso": Persona(1.2, "medo", 0.5), "assustadico": Persona(1.3, "medo", 0.7),
    "calmo": Persona(0.8), "calma": Persona(0.8), "sereno": Persona(0.75),
    "tranquilo": Persona(0.8), "frio": Persona(0.7), "firme": Persona(0.85),
    "cansado": Persona(0.9, "cansaco", 0.4), "cansada": Persona(0.9, "cansaco", 0.4),
    "raivoso": Persona(1.2, "raiva", 0.6), "explosivo": Persona(1.3, "raiva", 0.6),
    "alegre": Persona(1.1, "alegria", 0.4), "timido": Persona(1.1, "medo", 0.3),
    # EN
    "nervous": Persona(1.25, "medo", 0.6), "anxious": Persona(1.2, "medo", 0.5),
    "calm": Persona(0.8), "cold": Persona(0.7), "weary": Persona(0.9, "cansaco", 0.4),
    "angry": Persona(1.2, "raiva", 0.6), "cheerful": Persona(1.1, "alegria", 0.4),
    # ES
    "nervioso": Persona(1.25, "medo", 0.6), "tranquilo_es": Persona(0.8),
    "enojado": Persona(1.2, "raiva", 0.6),
}

_HOT = {"medo", "raiva", "urgencia", "surpresa"}   # emoções que "contagiam" a próxima


def personas_from_prose(characters, prose: str, lang: str = "pt") -> dict[str, Persona]:
    """Infere o temperamento de cada personagem dos descritores na prosa (uma frase
    com um só personagem credita a ele — evita cross-atribuição)."""
    chars = [c for c in characters if c and c not in ("Narrador", "?", "Personagem", "__EU__")]
    norm_names = {c: _norm(c) for c in chars}
    out: dict[str, Persona] = {}
    for sent in re.split(r"(?<=[.!?…])\s+", prose):
        wset = {_norm(w) for w in _WORD.findall(sent)}
        present = [c for c in chars if norm_names[c] in wset]
        if len(present) != 1:
            continue
        for w in wset:
            p = _TEMPERAMENT.get(w)
            if p and present[0] not in out:
                out[present[0]] = p
    return out


def _emo_table(lang: str) -> dict:
    key = str(lang or "pt").strip().lower()[:2]
    return _EMO_WORDS.get(key, _EMO_WORDS["pt"])


def infer_emotion(text: str, cue: str | None = None, scene_tension: float = 0.0,
                  prev_emotion: str = "neutro", persona: Persona | None = None,
                  lang: str = "pt") -> tuple[str, float]:
    """(emoção, intensidade 0..1) de UMA linha, a partir dos sinais da cena."""
    table = _emo_table(lang)
    scores: dict[str, float] = {}

    def add(emo, w):
        scores[emo] = scores.get(emo, 0.0) + w

    words = [_norm(w) for w in _WORD.findall(text)]
    for w in words:
        emo = table.get(w)
        if emo:
            add(emo, 1.0)

    cue_n = _norm(cue) if cue else ""
    if cue_n in _CUE_EMOTION:
        add(_CUE_EMOTION[cue_n], 1.2)

    excl = text.count("!")
    ell = "..." in text or text.strip().endswith("..")
    letters = [c for c in text if c.isalpha()]
    caps = sum(c.isupper() for c in letters) / len(letters) if letters else 0.0
    if excl:
        add("urgencia", 0.5 * excl)
        add("raiva", 0.25 * excl)
    if caps > 0.6 and len(letters) > 2:
        add("raiva", 1.0)
        add("urgencia", 0.6)
    if ell:
        add("suspense", 0.7)
    # clima da cena empurra o suspense/medo (sem inventar emoção onde não há sinal)
    if scene_tension > 0.45:
        add("suspense", 0.5 * scene_tension)
        add("medo", 0.3 * scene_tension)
    # persona: viés de temperamento
    if persona and persona.bias:
        add(persona.bias, persona.bias_weight)

    if not scores:
        # sem sinal: neutro, com um fio de tensão se a cena estiver quente
        return ("suspense" if scene_tension > 0.6 else "neutro",
                min(0.5, 0.2 + 0.4 * scene_tension))

    emotion = max(scores, key=lambda k: (scores[k], k))
    raw = scores[emotion]
    intensity = 0.35 + 0.22 * raw + 0.28 * scene_tension
    # reação (contágio): responder a uma linha "quente" sobe a carga
    if prev_emotion in _HOT:
        intensity += 0.1
    if persona:
        intensity *= persona.intensity_scale
    return emotion, max(0.0, min(1.0, intensity))


class SceneMood:
    """O termômetro da cena: sobe com falas carregadas e decai devagar. É o que faz
    uma sequência tensa 'contaminar' as falas seguintes com suspense."""

    def __init__(self, policy: EmotionPolicy | None = None, decay: float = 0.72):
        self.policy = policy or EmotionPolicy()
        self.decay = decay
        self.value = 0.0

    def update(self, emotion: str, intensity: float) -> float:
        """Move o termômetro em direção ao arousal da emoção (com decaimento). Devolve
        o novo valor."""
        arousal = self.policy.resolve(emotion, intensity).arousal
        self.value = max(arousal, self.value * self.decay)
        return self.value
