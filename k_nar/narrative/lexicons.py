"""Léxicos por IDIOMA para o Screenwriter (verbos de fala, gatilhos de som).

A segmentação estrutural (aspas → diálogo, quebra de frases) é agnóstica de idioma;
o que MUDA por idioma é o vocabulário: os verbos de fala que revelam o locutor e a
deixa, e as palavras que disparam SFX/ambiência. Cada idioma traz um `Lexicon`; as
CHAVES já vêm normalizadas (sem acento, minúsculas) porque o lookup usa `strip_accents`.

As TAGS de som são as do catálogo (`k_nar/sfx/catalog.py`), compartilhadas entre
idiomas — só o gatilho (a palavra) muda: "tiro"/"shot"/"disparo" → `tiro`.
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
    # palavras que revelam a DISTÂNCIA do som na frase ("ao longe", "perto").
    far_words: frozenset[str] = field(default_factory=frozenset)
    near_words: frozenset[str] = field(default_factory=frozenset)
    # palavras que revelam o ESPAÇO acústico → preset de reverb ("galpão" → galpao_vazio).
    space_triggers: dict[str, str] = field(default_factory=dict)
    # CÔMODOS → preset de reverb, p/ o "set virtual" de zonas (Nível 1). Quando o POV
    # anda de um cômodo a outro, o reverb o segue ("cozinha"→quarto_pequeno, "sala"→
    # sala_grande, "quintal"→seco/aberto). Mais amplo que space_triggers (que só pega o
    # espaço dominante de uma cena única).
    zone_triggers: dict[str, str] = field(default_factory=dict)
    # PESSOA narrativa: pronomes que revelam se a história é em 1ª pessoa (o próprio
    # personagem conta: "eu entrei") ou 3ª (um narrador conta: "ele entrou"). Contados
    # SÓ na narração (o diálogo sempre tem "eu"). Ver narrative/person.py.
    first_person: frozenset[str] = field(default_factory=frozenset)
    third_person: frozenset[str] = field(default_factory=frozenset)


# --------------------------------------------------------------------------- #
#  Português                                                                   #
# --------------------------------------------------------------------------- #
PT = Lexicon(
    speech_verbs=frozenset({
        # passado
        "disse", "falou", "perguntou", "respondeu", "gritou", "berrou", "exclamou",
        "sussurrou", "murmurou", "retrucou", "indagou", "replicou", "ordenou",
        "questionou", "afirmou", "declarou", "avisou", "alertou", "gaguejou",
        "cochichou", "bradou", "vociferou", "resmungou", "pediu", "insistiu",
        "continuou", "concluiu", "acrescentou", "completou", "chamou", "comentou",
        # presente (narração no presente é comum na literatura em PT)
        "diz", "fala", "pergunta", "responde", "grita", "berra", "exclama",
        "sussurra", "murmura", "retruca", "indaga", "replica", "ordena", "pede",
        "insiste", "continua", "conclui", "acrescenta", "completa", "chama",
        "comenta", "resmunga", "brada", "avisa", "alerta", "cochicha", "gagueja",
    }),
    loud_verbs=frozenset({
        "gritou", "berrou", "exclamou", "bradou", "vociferou", "ordenou", "alertou",
        "grita", "berra", "exclama", "brada", "ordena", "alerta",
    }),
    soft_verbs=frozenset({
        "sussurrou", "murmurou", "cochichou", "gaguejou", "resmungou",
        "sussurra", "murmura", "cochicha", "gagueja", "resmunga",
    }),
    not_names=frozenset({
        "a", "o", "e", "ele", "ela", "eles", "elas", "entao", "mas", "quando",
        "de", "do", "da", "no", "na", "com", "por", "que", "um", "uma", "os", "as",
        "seu", "sua", "isso", "aquilo", "aquele", "aquela", "depois", "antes",
    }),
    sfx_triggers={
        # portas / impacto (o SOM vem do VERBO — "porta" sozinha é objeto, não som)
        "rangeu": "porta_range", "range": "porta_range", "rangendo": "porta_range",
        "ranger": "porta_range", "rangido": "porta_range", "bateu": "batida",
        "pancada": "batida", "socou": "batida", "martelou": "batida", "batendo": "batida",
        # passos
        "passos": "passos", "pisou": "passos", "pisadas": "passos", "poca": "passos_poca",
        # vidro / armas / explosão
        "estilhacou": "vidro_quebra", "quebrou": "vidro_quebra",
        "despedacou": "vidro_quebra", "tiro": "tiro", "tiros": "tiro", "disparo": "tiro",
        "disparou": "tiro", "atirou": "tiro", "pistola": "tiro", "revolver": "tiro",
        "explosao": "explosao", "explodiu": "explosao", "estourou": "explosao",
        "detonou": "explosao", "bomba": "explosao", "fogos": "fogos", "rojao": "fogos",
        # natureza pontual
        "trovao": "trovao", "trovejou": "trovao", "raio": "trovao", "relampago": "trovao",
        "pingo": "pingo", "pingou": "pingo", "gotejou": "pingo", "gota": "pingo",
        "gotejando": "pingo", "torneira": "pingo", "derramou": "agua_derramando",
        "jorrou": "agua_derramando", "despejou": "agua_derramando",
        # eletrônico / sinais
        "sirene": "sirene", "alarme": "alarme", "sino": "sino", "sinos": "sino",
        "badalada": "sino", "badalou": "sino", "chiado": "estatica", "chiou": "estatica",
        "estatica": "estatica", "interferencia": "estatica", "discagem": "tom_discagem",
        "ocupado": "linha_ocupada", "bipe": "bipe", "bip": "bipe",
        # objetos / foley
        "teclado": "teclado", "digitou": "teclado", "datilografou": "teclado",
        "descarga": "descarga", "lata": "lata_abrindo", "buzina": "buzina", "buzinou": "buzina",
        # animais (pontuais)
        "cachorro": "cachorro", "cao": "cachorro", "latido": "cachorro", "latiu": "cachorro",
        "latindo": "cachorro", "gato": "gato", "miou": "gato", "corvo": "corvo",
        "grasnou": "corvo", "galo": "galo", "galinha": "galinha", "cacarejou": "galinha",
        "vaca": "vaca", "mugiu": "vaca", "porco": "porco", "grunhiu": "porco",
        "ovelha": "ovelha", "balou": "ovelha", "coaxou": "ra", "sapo": "ra",
        # humano não-verbal
        "tossiu": "tosse", "tosse": "tosse", "espirro": "espirro", "espirrou": "espirro",
        "roncou": "ronco", "ronco": "ronco", "palmas": "palmas", "aplausos": "palmas",
        "aplaudiu": "palmas", "risada": "risada", "gargalhou": "risada", "gargalhada": "risada",
        # máquinas
        "motosserra": "motosserra", "serrote": "serra", "aviao": "aviao", "jato": "aviao",
        "trem": "trem", "locomotiva": "trem",
    },
    ambience_triggers={
        "grilos": "grilos", "grilo": "grilos", "floresta": "floresta_noite",
        "mata": "floresta_noite", "selva": "floresta_noite", "bosque": "floresta_noite",
        "insetos": "insetos", "cigarras": "insetos", "cigarra": "insetos",
        "chuva": "chuva", "chovia": "chuva", "chovendo": "chuva", "temporal": "chuva",
        "aguaceiro": "chuva", "tempestade": "tempestade",
        "vento": "vento", "ventania": "vento", "brisa": "vento", "ventava": "vento",
        "mar": "oceano", "oceano": "oceano", "ondas": "oceano", "maresia": "oceano",
        "fogo": "fogo", "fogueira": "fogo", "chamas": "fogo", "lareira": "fogo",
        "crepitava": "fogo", "motor": "motor", "motores": "motor", "zumbido": "motor",
        "nave": "motor", "gerador": "motor", "zunido": "transformador",
        "transformador": "transformador", "transito": "cidade",
        "multidao": "multidao", "plateia": "multidao", "torcida": "multidao",
        "passaros": "passaros", "helicoptero": "helicoptero", "aspirador": "aspirador",
        "relogio": "relogio", "tiquetaque": "relogio",
    },
    far_words=frozenset({"longe", "distante", "distancia", "afastado", "remoto",
                         "lonjura", "horizonte", "distantes", "alem"}),
    near_words=frozenset({"perto", "proximo", "junto", "rente", "colado", "pertinho",
                          "ladinho", "adiante"}),
    space_triggers={
        "galpao": "galpao_vazio", "armazem": "galpao_vazio", "hangar": "galpao_vazio",
        "salao": "galpao_vazio", "catedral": "catedral", "igreja": "catedral",
        "capela": "catedral", "caverna": "caverna", "gruta": "caverna",
        "tunel": "tunel", "banheiro": "banheiro",
    },
    zone_triggers={
        "cozinha": "quarto_pequeno", "sala": "sala_grande", "quarto": "quarto_pequeno",
        "dormitorio": "quarto_pequeno", "escritorio": "quarto_pequeno", "cela": "quarto_pequeno",
        "corredor": "corredor_estreito", "hall": "corredor_estreito", "saguao": "corredor_estreito",
        "porao": "caverna", "adega": "caverna", "sotao": "quarto_pequeno",
        "garagem": "galpao_vazio", "galpao": "galpao_vazio", "armazem": "galpao_vazio",
        "celeiro": "galpao_vazio", "salao": "galpao_vazio", "hangar": "galpao_vazio",
        "banheiro": "banheiro", "lavabo": "banheiro",
        "quintal": "seco", "patio": "seco", "jardim": "seco", "rua": "seco",
        "campo": "seco", "varanda": "seco", "alpendre": "seco", "terraco": "seco",
        "igreja": "catedral", "catedral": "catedral", "capela": "catedral",
        "caverna": "caverna", "gruta": "caverna", "tunel": "tunel",
    },
    first_person=frozenset({"eu", "meu", "minha", "meus", "minhas", "me", "mim",
                            "comigo", "nos", "nossa", "nosso"}),
    third_person=frozenset({"ele", "ela", "eles", "elas", "dele", "dela", "deles",
                            "delas", "lhe"}),
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
        "creaked": "porta_range", "creak": "porta_range",
        "creaking": "porta_range", "banged": "batida",
        "bang": "batida", "knock": "batida", "knocked": "batida", "pounded": "batida",
        "footsteps": "passos", "steps": "passos", "puddle": "passos_poca",
        "shattered": "vidro_quebra", "smashed": "vidro_quebra",
        "gunshot": "tiro", "shot": "tiro", "fired": "tiro", "gunfire": "tiro", "pistol": "tiro",
        "exploded": "explosao", "explosion": "explosao", "blast": "explosao", "bomb": "explosao",
        "fireworks": "fogos", "thunder": "trovao", "thundered": "trovao", "lightning": "trovao",
        "drip": "pingo", "dripped": "pingo", "dripping": "pingo", "faucet": "pingo",
        "siren": "sirene", "alarm": "alarme", "bell": "sino", "bells": "sino", "tolled": "sino",
        "static": "estatica", "interference": "estatica", "dial": "tom_discagem", "beep": "bipe",
        "keyboard": "teclado", "typing": "teclado", "typewriter": "teclado", "horn": "buzina",
        "dog": "cachorro", "barked": "cachorro", "barking": "cachorro", "cat": "gato",
        "meowed": "gato", "crow": "corvo", "rooster": "galo", "cow": "vaca", "mooed": "vaca",
        "coughed": "tosse", "cough": "tosse", "sneezed": "espirro", "snored": "ronco",
        "clapped": "palmas", "applause": "palmas", "laughed": "risada", "laughter": "risada",
        "chainsaw": "motosserra", "airplane": "aviao", "plane": "aviao", "train": "trem",
    },
    ambience_triggers={
        "crickets": "grilos", "forest": "floresta_noite", "woods": "floresta_noite",
        "jungle": "floresta_noite", "insects": "insetos", "cicadas": "insetos",
        "rain": "chuva", "raining": "chuva", "storm": "tempestade", "downpour": "chuva",
        "wind": "vento", "breeze": "vento", "gale": "vento", "ocean": "oceano",
        "sea": "oceano", "waves": "oceano", "fire": "fogo", "campfire": "fogo",
        "fireplace": "fogo", "flames": "fogo", "engine": "motor", "engines": "motor",
        "hum": "motor", "ship": "motor", "generator": "motor", "buzz": "transformador",
        "transformer": "transformador", "traffic": "cidade",
        "crowd": "multidao", "birds": "passaros", "helicopter": "helicoptero",
        "clock": "relogio",
    },
    far_words=frozenset({"far", "distant", "distance", "faraway", "afar", "remote",
                         "horizon", "yonder"}),
    near_words=frozenset({"near", "close", "nearby", "beside", "closeup"}),
    space_triggers={
        "warehouse": "galpao_vazio", "hangar": "galpao_vazio", "cathedral": "catedral",
        "church": "catedral", "chapel": "catedral", "cave": "caverna", "cavern": "caverna",
        "tunnel": "tunel", "bathroom": "banheiro",
    },
    zone_triggers={
        "kitchen": "quarto_pequeno", "bedroom": "quarto_pequeno", "office": "quarto_pequeno",
        "study": "quarto_pequeno", "cell": "quarto_pequeno", "attic": "quarto_pequeno",
        "corridor": "corredor_estreito", "hallway": "corredor_estreito", "hall": "corredor_estreito",
        "basement": "caverna", "cellar": "caverna", "garage": "galpao_vazio",
        "warehouse": "galpao_vazio", "barn": "galpao_vazio", "hangar": "galpao_vazio",
        "bathroom": "banheiro", "restroom": "banheiro",
        "yard": "seco", "garden": "seco", "street": "seco", "field": "seco",
        "porch": "seco", "balcony": "seco", "terrace": "seco",
        "church": "catedral", "cathedral": "catedral", "chapel": "catedral",
        "cave": "caverna", "cavern": "caverna", "tunnel": "tunel",
    },
    first_person=frozenset({"i", "me", "my", "mine", "myself", "we", "our", "us"}),
    third_person=frozenset({"he", "she", "they", "him", "her", "his", "hers",
                            "them", "their"}),
)

# --------------------------------------------------------------------------- #
#  Español                                                                     #
# --------------------------------------------------------------------------- #
ES = Lexicon(
    speech_verbs=frozenset({
        # pasado
        "dijo", "pregunto", "respondio", "grito", "susurro", "murmuro", "exclamo",
        "contesto", "replico", "ordeno", "afirmo", "declaro", "aviso", "advirtio",
        "balbuceo", "farfullo", "bramo", "rugio", "pidio", "insistio", "continuo",
        "anadio", "llamo", "chillo",
        # presente
        "dice", "pregunta", "responde", "grita", "susurra", "murmura", "exclama",
        "contesta", "replica", "ordena", "pide", "insiste", "continua", "llama",
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
        "golpeo": "batida", "golpe": "batida", "toco": "batida",
        "pasos": "passos", "charco": "passos_poca",
        "rompio": "vidro_quebra", "estallo": "explosao", "disparo": "tiro", "tiro": "tiro",
        "disparos": "tiro", "pistola": "tiro", "explosion": "explosao", "bomba": "explosao",
        "trueno": "trovao", "rayo": "trovao", "relampago": "trovao", "goteo": "pingo",
        "gota": "pingo", "grifo": "pingo", "sirena": "sirene", "alarma": "alarme",
        "campana": "sino", "campanas": "sino", "estatica": "estatica", "interferencia": "estatica",
        "teclado": "teclado", "bocina": "buzina", "perro": "cachorro", "ladro": "cachorro",
        "gato": "gato", "cuervo": "corvo", "gallo": "galo", "vaca": "vaca",
        "toso": "tosse", "estornudo": "espirro", "ronco": "ronco", "aplausos": "palmas",
        "risa": "risada", "avion": "aviao", "tren": "trem",
    },
    ambience_triggers={
        "grillos": "grilos", "bosque": "floresta_noite", "selva": "floresta_noite",
        "insectos": "insetos", "lluvia": "chuva", "llovia": "chuva", "tormenta": "tempestade",
        "viento": "vento", "brisa": "vento", "mar": "oceano", "olas": "oceano",
        "fuego": "fogo", "fogata": "fogo", "chimenea": "fogo", "motor": "motor",
        "motores": "motor", "zumbido": "motor", "nave": "motor", "transformador": "transformador",
        "multitud": "multidao", "pajaros": "passaros",
        "helicoptero": "helicoptero", "reloj": "relogio",
    },
    far_words=frozenset({"lejos", "distante", "distancia", "lejano", "remoto", "horizonte"}),
    near_words=frozenset({"cerca", "cercano", "junto", "proximo", "pegado"}),
    space_triggers={
        "galpon": "galpao_vazio", "almacen": "galpao_vazio",
        "catedral": "catedral", "iglesia": "catedral", "cueva": "caverna",
        "caverna": "caverna", "tunel": "tunel", "bano": "banheiro",
    },
    zone_triggers={
        "cocina": "quarto_pequeno", "sala": "sala_grande", "cuarto": "quarto_pequeno",
        "habitacion": "quarto_pequeno", "dormitorio": "quarto_pequeno", "oficina": "quarto_pequeno",
        "celda": "quarto_pequeno", "desvan": "quarto_pequeno",
        "pasillo": "corredor_estreito", "corredor": "corredor_estreito",
        "sotano": "caverna", "bodega": "caverna", "garaje": "galpao_vazio",
        "almacen": "galpao_vazio", "granero": "galpao_vazio", "salon": "galpao_vazio",
        "bano": "banheiro", "patio": "seco", "jardin": "seco", "calle": "seco",
        "campo": "seco", "balcon": "seco", "terraza": "seco",
        "iglesia": "catedral", "catedral": "catedral", "capilla": "catedral",
        "cueva": "caverna", "caverna": "caverna", "tunel": "tunel",
    },
    # "el" (artigo) é ambíguo em ES → fora; usamos pronomes inequívocos de 3ª pessoa.
    first_person=frozenset({"yo", "mi", "mis", "me", "conmigo", "mio", "mia",
                            "nosotros", "nuestra", "nuestro"}),
    third_person=frozenset({"ella", "ellos", "ellas", "le", "les", "suyo", "suya"}),
)

LEXICONS: dict[str, Lexicon] = {
    "pt": PT, "pt_br": PT, "pt-br": PT, "portugues": PT,
    "en": EN, "en_us": EN, "en-us": EN, "english": EN, "ingles": EN,
    "es": ES, "es_es": ES, "es-es": ES, "espanol": ES, "spanish": ES,
}


def get_lexicon(lang: str) -> Lexicon:
    """Léxico do idioma (default PT). Aceita 'pt', 'en_US', 'espanol'..."""
    return LEXICONS.get(str(lang).strip().lower().replace(" ", ""), PT)
