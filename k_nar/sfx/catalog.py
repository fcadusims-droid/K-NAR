"""Catálogo de sons — a taxonomia ÚNICA do K-NAR (tag → categoria, ambiência, fonte).

Cada som tem uma `tag` canônica. Se houver uma categoria ESC-50 equivalente, o
`LibrarySfxBackend` usa o sample REAL de lá; senão (sons eletrônicos/armas que o
ESC-50 não cobre), o `ProceduralSfxBackend` sintetiza. Os apelidos por idioma que
disparam cada tag na prosa ficam em `narrative/lexicons.py` e referenciam estas tags.

    from k_nar.sfx.catalog import CATALOG, AMBIENCE_TAGS, esc50_category
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SoundDef:
    tag: str
    category: str            # natureza | animais | foley | mecanico | eletronico | impacto | humano
    ambience: bool = False   # True = cama contínua (loopável); False = som pontual
    esc50: str | None = None  # categoria ESC-50 que fornece o sample real (None = procedural)


# --------------------------------------------------------------------------- #
#  O catálogo. `esc50` != None => há sample real; None => síntese procedural.  #
# --------------------------------------------------------------------------- #
_SOUNDS: tuple[SoundDef, ...] = (
    # --- Natureza / ambiências (camas) ---
    SoundDef("grilos", "natureza", ambience=True, esc50="crickets"),
    SoundDef("floresta_noite", "natureza", ambience=True, esc50="crickets"),
    SoundDef("insetos", "natureza", ambience=True, esc50="insects"),
    SoundDef("chuva", "natureza", ambience=True, esc50="rain"),
    SoundDef("vento", "natureza", ambience=True, esc50="wind"),
    SoundDef("oceano", "natureza", ambience=True, esc50="sea_waves"),
    SoundDef("fogo", "natureza", ambience=True, esc50="crackling_fire"),
    SoundDef("passaros", "natureza", ambience=True, esc50="chirping_birds"),

    # --- Natureza / pontuais ---
    SoundDef("trovao", "natureza", esc50="thunderstorm"),
    SoundDef("tempestade", "natureza", ambience=True, esc50="thunderstorm"),
    SoundDef("agua_derramando", "natureza", esc50="pouring_water"),
    SoundDef("pingo", "natureza", esc50="water_drops"),

    # --- Animais ---
    SoundDef("cachorro", "animais", esc50="dog"),
    SoundDef("gato", "animais", esc50="cat"),
    SoundDef("passaro", "animais", esc50="chirping_birds"),
    SoundDef("corvo", "animais", esc50="crow"),
    SoundDef("galo", "animais", esc50="rooster"),
    SoundDef("galinha", "animais", esc50="hen"),
    SoundDef("vaca", "animais", esc50="cow"),
    SoundDef("porco", "animais", esc50="pig"),
    SoundDef("ovelha", "animais", esc50="sheep"),
    SoundDef("ra", "animais", esc50="frog"),

    # --- Foley / portas / objetos ---
    SoundDef("porta_range", "foley", esc50="door_wood_creaks"),
    SoundDef("batida", "foley", esc50="door_wood_knock"),
    SoundDef("passos", "foley", esc50="footsteps"),
    SoundDef("passos_poca", "foley"),                 # splash: procedural
    SoundDef("vidro_quebra", "impacto", esc50="glass_breaking"),
    SoundDef("relogio", "foley", ambience=True, esc50="clock_tick"),
    SoundDef("teclado", "foley", esc50="keyboard_typing"),
    SoundDef("descarga", "foley", esc50="toilet_flush"),
    SoundDef("lata_abrindo", "foley", esc50="can_opening"),

    # --- Mecânico / veículos ---
    SoundDef("motor", "mecanico", ambience=True, esc50="engine"),
    SoundDef("aviao", "mecanico", esc50="airplane"),
    SoundDef("helicoptero", "mecanico", ambience=True, esc50="helicopter"),
    SoundDef("trem", "mecanico", esc50="train"),
    SoundDef("buzina", "mecanico", esc50="car_horn"),
    SoundDef("aspirador", "mecanico", ambience=True, esc50="vacuum_cleaner"),
    SoundDef("motosserra", "mecanico", esc50="chainsaw"),
    SoundDef("serra", "mecanico", esc50="hand_saw"),
    SoundDef("maquina_lavar", "mecanico", ambience=True, esc50="washing_machine"),

    # --- Sinais / alarmes ---
    SoundDef("sirene", "eletronico", esc50="siren"),
    SoundDef("alarme", "eletronico", esc50="clock_alarm"),
    SoundDef("sino", "eletronico", esc50="church_bells"),
    SoundDef("fogos", "impacto", esc50="fireworks"),

    # --- Humano (não-verbal) ---
    SoundDef("tosse", "humano", esc50="coughing"),
    SoundDef("respiracao", "humano", esc50="breathing"),
    SoundDef("risada", "humano", esc50="laughing"),
    SoundDef("espirro", "humano", esc50="sneezing"),
    SoundDef("ronco", "humano", esc50="snoring"),
    SoundDef("palmas", "humano", esc50="clapping"),
    SoundDef("choro", "humano", esc50="crying_baby"),

    # --- Impacto / armas (procedural: ESC-50 não cobre) ---
    SoundDef("tiro", "impacto"),
    SoundDef("explosao", "impacto"),

    # --- Eletrônico (procedural: síntese faz melhor) ---
    SoundDef("estatica", "eletronico", ambience=True),      # chiado de rádio
    SoundDef("tom_discagem", "eletronico"),                 # tom de discar
    SoundDef("linha_ocupada", "eletronico"),                # sinal de ocupado
    SoundDef("transformador", "eletronico", ambience=True), # zunido elétrico
    SoundDef("bipe", "eletronico"),

    # --- Multidão / cidade (procedural) ---
    SoundDef("multidao", "humano", ambience=True),
    SoundDef("cidade", "mecanico", ambience=True),
)

CATALOG: dict[str, SoundDef] = {s.tag: s for s in _SOUNDS}
AMBIENCE_TAGS: frozenset[str] = frozenset(s.tag for s in _SOUNDS if s.ambience)

# tag -> categoria ESC-50 (só as que têm sample real)
ESC50_MAP: dict[str, str] = {s.tag: s.esc50 for s in _SOUNDS if s.esc50}
# categoria ESC-50 -> lista de tags que a usam (para o baixador saber o que buscar)
ESC50_CATEGORIES: dict[str, list[str]] = {}
for _s in _SOUNDS:
    if _s.esc50:
        ESC50_CATEGORIES.setdefault(_s.esc50, []).append(_s.tag)


def esc50_category(tag: str) -> str | None:
    s = CATALOG.get(tag)
    return s.esc50 if s else None


def is_ambience(tag: str) -> bool:
    return tag in AMBIENCE_TAGS
