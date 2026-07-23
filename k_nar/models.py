"""Modelo de dados da PASSAGEM 1 (o LLM como Diretor de Palco).

Regra de ouro: o LLM nunca cospe segundos nem Hz absolutos. Ele só descreve
*intenção relativa* (tensão, agressividade da interrupção, tipo de pausa). A
tradução para milissegundos acontece depois, no `TimingPolicy`, já de posse da
duração real medida pelo TTS. É isso que quebra a dependência circular
"preciso do tempo pra montar a cena, mas o tempo só existe depois de sintetizar".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Union


class EntryType(str, Enum):
    """Como esta fala entra em relação à anterior."""

    SEQUENTIAL = "sequencial"     # começa depois da fala anterior (+ pausa)
    INTERRUPTION = "interrupcao"  # corta o final da fala anterior (o anterior é "engolido")
    OVERLAP = "sobreposicao"      # fala simultânea; ninguém é cortado, as duas coexistem


class DramaticPause(str, Enum):
    """Silêncio dramático DEPOIS da fala. Rótulo qualitativo; o valor em ms
    vive no TimingPolicy."""

    NONE = "nenhuma"
    SHORT = "curta"
    MEDIUM = "media"
    LONG = "longa"


class Track(str, Enum):
    """A TRILHA (bus) onde um evento é mixado. É o discriminador que generaliza a
    linha de tempo de "só diálogo" para áudio narrativo: diálogo e narração são fala
    (mesmo TTS) em buses distintos; SFX/ambiência/música entram nas fases seguintes.
    O renderer mixa por trilha — pré-requisito do ducking (ambiência afunda sob a fala)."""

    DIALOGUE = "dialogo"
    NARRATION = "narracao"
    SFX = "sfx"
    AMBIENCE = "ambiencia"
    MUSIC = "musica"


# Rótulos qualitativos de tensão -> escalar 0..1. FONTE ÚNICA, lida pelo TimingPolicy
# (default sobrescrevível por "estilo de direção"), pela ProsodyPolicy e pelo Formant.
TENSION_LABELS = {"baixa": 0.15, "media": 0.5, "alta": 0.8, "extrema": 1.0}


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class VoiceParams:
    """Parâmetros RELATIVOS de performance passados ao TTS.

    `tension` pode chegar como número (0..1) ou rótulo ("alta", "extrema"); o
    rótulo é resolvido pelo TimingPolicy para manter todos os "números mágicos"
    num lugar só. Nada aqui é absoluto: `rate` é multiplicador, `pitch` é desvio.
    """

    tension: Any = 0.0   # 0.0 calmo -> 1.0 pânico/fúria  (float ou rótulo)
    rate: float = 1.0    # multiplicador de velocidade (1.0 = neutro)
    pitch: float = 0.0   # desvio relativo de tom (-1.0 .. +1.0), 0 = neutro

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "VoiceParams":
        d = d or {}
        return cls(
            tension=d.get("tensao", d.get("tension", 0.0)),
            rate=_as_float(d.get("velocidade", d.get("rate", 1.0)), 1.0),
            pitch=_as_float(d.get("tom", d.get("pitch", 0.0)), 0.0),
        )


@dataclass
class EntryDynamics:
    """Dinâmica de ENTRADA — o metadado relativo que o código traduz em ms."""

    type: EntryType = EntryType.SEQUENTIAL
    # 0.0..1.0 — fração da fala anterior a "comer" (só vale p/ interrupção/sobreposição).
    # 0.25 = corta os últimos 25% do anterior.
    aggressiveness: float = 0.0

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "EntryDynamics":
        d = d or {}
        raw_type = d.get("tipo", d.get("type", EntryType.SEQUENTIAL.value))
        try:
            etype = EntryType(raw_type)
        except ValueError:
            etype = EntryType.SEQUENTIAL
        return cls(
            type=etype,
            aggressiveness=_as_float(d.get("agressividade", d.get("aggressiveness", 0.0)), 0.0),
        )


@dataclass
class ExitDynamics:
    """Dinâmica de SAÍDA — a pausa dramática que separa esta fala da próxima."""

    dramatic_pause: DramaticPause = DramaticPause.NONE

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "ExitDynamics":
        d = d or {}
        raw = d.get("pausa", d.get("pausa_dramatica", d.get("dramatic_pause", "nenhuma")))
        try:
            pause = DramaticPause(raw)
        except ValueError:
            pause = DramaticPause.NONE
        return cls(dramatic_pause=pause)


@dataclass
class SpeechEvent:
    """Um evento de fala (diálogo). É a unidade que o TTS sintetiza e que o
    Orquestrador posiciona na linha de tempo."""

    id: str
    character: str
    text: str
    voice: VoiceParams = field(default_factory=VoiceParams)
    entry: EntryDynamics = field(default_factory=EntryDynamics)
    exit: ExitDynamics = field(default_factory=ExitDynamics)
    pan: int = 0  # posição no palco estéreo (-100 esquerda .. +100 direita); usado pelo DSP depois
    track: Track = Track.DIALOGUE  # bus de mixagem (discriminador do evento)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SpeechEvent":
        palco = d.get("palco", {}) or {}
        pan = int(_as_float(palco.get("estereo", palco.get("pan", d.get("posicao_estereo", 0))), 0.0))
        return cls(
            id=str(d["id"]),
            character=str(d.get("personagem", d.get("character", "?"))),
            text=str(d.get("texto", d.get("text", ""))),
            voice=VoiceParams.from_dict(d.get("voz", d.get("parametros_voz"))),
            entry=EntryDynamics.from_dict(d.get("entrada", d.get("dinamica_de_entrada"))),
            exit=ExitDynamics.from_dict(d.get("saida", d.get("dinamica_de_saida"))),
            pan=pan,
        )


@dataclass
class NarrationEvent:
    """A voz do NARRADOR. É fala (mesmo TTS que o diálogo), mas noutra trilha: entra
    sempre em sequência (o narrador não é interrompido), centralizada por padrão.

    Expõe a MESMA interface de duck-typing que `SpeechEvent` (`.id/.character/.text/
    .voice/.entry/.exit/.pan`) para o Orquestrador tratar os dois no mesmo laço; só o
    `.track` os separa no mix."""

    id: str
    text: str
    voice: VoiceParams = field(default_factory=VoiceParams)
    exit: ExitDynamics = field(default_factory=ExitDynamics)
    character: str = "Narrador"
    pan: int = 0
    entry: EntryDynamics = field(default_factory=EntryDynamics)  # sempre sequencial
    track: Track = Track.NARRATION

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "NarrationEvent":
        palco = d.get("palco", {}) or {}
        pan = int(_as_float(palco.get("estereo", palco.get("pan", 0)), 0.0))
        return cls(
            id=str(d["id"]),
            text=str(d.get("texto", d.get("text", ""))),
            character=str(d.get("personagem", d.get("character", "Narrador"))),
            voice=VoiceParams.from_dict(d.get("voz", d.get("parametros_voz"))),
            exit=ExitDynamics.from_dict(d.get("saida", d.get("dinamica_de_saida"))),
            pan=pan,
        )


@dataclass
class SfxEvent:
    """Efeito sonoro PONTUAL (foley). O `tag` é o que buscar na biblioteca de sons
    (`tiro`, `passos_poca`, `porta_range`) — NÃO é fala e o narrador não o lê. A
    duração vem do sample REAL medido (mesma tese das duas passagens: intenção
    relativa → ms reais), então uma fala pode ser ancorada p/ reagir ao som."""

    id: str
    tag: str
    gain_db: float = -3.0                 # nível relativo no mix
    pan: int = 0
    entry: EntryDynamics = field(default_factory=EntryDynamics)  # timing na linha
    exit: ExitDynamics = field(default_factory=ExitDynamics)
    track: Track = Track.SFX
    character: str = ""                    # duck-typing c/ o Orquestrador (sem voz)
    text: str = ""                         # descrição opcional (nunca falada)
    # DISTÂNCIA do som: "perto" | "media" | "longe" | "muito_longe". O `ProximityPolicy`
    # traduz em nível + abafamento (o ar come os agudos de longe) + largura estéreo —
    # "tiros ao longe" ≠ "à queima-roupa".
    distance: str = "media"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SfxEvent":
        palco = d.get("palco", {}) or {}
        return cls(
            id=str(d["id"]),
            tag=str(d.get("tag", d.get("gatilho", d.get("som", "")))),
            gain_db=_as_float(d.get("ganho_db", d.get("gain_db", -3.0)), -3.0),
            pan=int(_as_float(palco.get("estereo", palco.get("pan", 0)), 0.0)),
            entry=EntryDynamics.from_dict(d.get("entrada", d.get("dinamica_de_entrada"))),
            exit=ExitDynamics.from_dict(d.get("saida", d.get("dinamica_de_saida"))),
            text=str(d.get("texto", d.get("descricao", ""))),
            distance=str(d.get("distancia", d.get("distance", "media"))).strip().lower(),
        )


@dataclass
class AmbienceEvent:
    """Cama AMBIENTAL que cobre a cena inteira (`floresta_noite`, `chuva`, `motor`).
    Loopável e baixa (fundo); o ducking a faz afundar sob a fala. Não entra na
    sequência temporal — é um bed, não um evento pontual."""

    id: str
    tag: str
    gain_db: float = -20.0                 # baixa por padrão (fundo)
    track: Track = Track.AMBIENCE
    character: str = ""
    text: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AmbienceEvent":
        return cls(
            id=str(d["id"]),
            tag=str(d.get("tag", d.get("ambiente", d.get("som", "")))),
            gain_db=_as_float(d.get("ganho_db", d.get("gain_db", -20.0)), -20.0),
            text=str(d.get("texto", d.get("descricao", ""))),
        )


# Evento de linha de tempo (união de tipos). `SpeechEvent`/`NarrationEvent` são fala;
# `SfxEvent`/`AmbienceEvent` são som. Todos compartilham a interface de duck-typing que
# o Orquestrador consome (.id/.character/.text/.track [+ .entry/.exit/.pan p/ sequenciáveis]).
Event = Union[SpeechEvent, NarrationEvent, SfxEvent, AmbienceEvent]

# Dispatcher: lê o discriminador do JSON e constrói o evento certo.
_EVENT_BUILDERS = {
    "fala": SpeechEvent.from_dict,
    "dialogo": SpeechEvent.from_dict,
    "narracao": NarrationEvent.from_dict,
    "narrador": NarrationEvent.from_dict,
    "sfx": SfxEvent.from_dict,
    "som": SfxEvent.from_dict,
    "efeito": SfxEvent.from_dict,
    "ambiencia": AmbienceEvent.from_dict,
    "ambience": AmbienceEvent.from_dict,
    "ambiente": AmbienceEvent.from_dict,
}


def build_event(d: dict[str, Any]):
    """Constrói o evento certo conforme `tipo_evento` (default: fala). Também trata
    `personagem: "Narrador"` como narração, por ergonomia."""
    kind = str(d.get("tipo_evento", d.get("tipo", d.get("kind", "")))).strip().lower()
    if not kind and str(d.get("personagem", d.get("character", ""))).strip().lower() in ("narrador", "narrator"):
        kind = "narracao"
    return _EVENT_BUILDERS.get(kind, SpeechEvent.from_dict)(d)


@dataclass
class Scene:
    """Uma cena: identidade acústica (`ambiance` -> Impulse Response no DSP) + eventos."""

    id: str
    ambiance: str
    events: list[Any] = field(default_factory=list)  # SpeechEvent | NarrationEvent

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Scene":
        eventos = d.get("eventos", d.get("events", []))
        return cls(
            id=str(d.get("cena_id", d.get("id", "cena"))),
            ambiance=str(d.get("ambientacao", d.get("ambiance", "seco"))),
            events=[build_event(e) for e in eventos],
        )
