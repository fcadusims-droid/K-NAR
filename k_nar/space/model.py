"""SceneModel — o "set virtual" acústico do K-NAR (Nível 1).

A tese: sair dos RÓTULOS de espaço escolhidos à mão ("longe", "galpão vazio") e
DERIVAR a acústica de um MODELO da cena — um mapa de ZONAS (cômodos), quem está em
cada uma e por onde o ouvinte (o POV) anda. É a mesma filosofia do resto do motor,
agora aplicada ao espaço: "posição relativa → o código resolve os números".

Não é física de raios (caro, frágil e quase inaudível em estéreo — ver ROADMAP). É
um GRAFO de zonas: cada zona tem um preset de reverb (o cômodo em que você está), e
a adjacência (portas/passagens) diz o quanto uma parede separa uma fonte do ouvinte.
Disso saem três coisas que o renderer já sabe aplicar:

    reverb   = o preset da zona do OUVINTE (o cômodo onde ele está)
    distância= perto/longe conforme a fonte está na mesma zona ou noutra
    oclusão  = 0..1, quanto a parede abafa a fonte (é "o som bate e volta")

O `SceneModel` é DADO PURO (stdlib): resolve `SpatialCue`s que o Orquestrador grava
na EDL; o renderer só aplica. Serializa/desserializa para atravessar o Screenwriter.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


# Amortecimento (absorção) PADRÃO por preset: quanto o cômodo "engole" o reverb. Um
# cômodo mobiliado/em uso (quarto, escritório, sala com móveis) absorve MUITO → quase
# seco; um espaço grande e NU (galpão, catedral, caverna) reverbera de verdade. É o que
# separa "sala em uso" (seca) de "galpão vazio" (eco). 0 = vivo/nu; 1 = totalmente seco.
PRESET_DAMPING = {
    "quarto_pequeno": 0.78, "banheiro": 0.35, "corredor_estreito": 0.55,
    "sala_grande": 0.65, "cockpit_metalico_eco": 0.45,
    "galpao_vazio": 0.12, "catedral": 0.08, "caverna": 0.12, "tunel": 0.20,
    "seco": 1.0,
}


def default_damping(preset: str) -> float:
    """Amortecimento padrão de um preset (cômodo mobiliado é o caso comum → seco)."""
    return PRESET_DAMPING.get(preset, 0.65)


@dataclass(frozen=True)
class Zone:
    """Um cômodo/zona acústica. `space` é a chave do preset de reverb (impulse.py):
    'quarto_pequeno', 'sala_grande', 'galpao_vazio', 'seco' (aberto), etc.

    `damping` (0..1) é a ABSORÇÃO do cômodo: mobiliado/em uso → alto (seco); vazio/nu →
    baixo (eco). None = usa o padrão do preset (`default_damping`)."""

    id: str
    space: str = "seco"
    name: str = ""
    damping: float | None = None

    @property
    def effective_damping(self) -> float:
        return default_damping(self.space) if self.damping is None else self.damping


@dataclass(frozen=True)
class SpatialCue:
    """O que o modelo resolve para UM evento: o reverb do cômodo do ouvinte, a
    distância (mesma zona vs. outra) e a oclusão (quanto de parede há no caminho)."""

    space: str          # preset de reverb da zona do OUVINTE
    distance: str       # rótulo p/ a ProximityPolicy ("perto"/"media"/"longe"/"muito_longe")
    occlusion: float    # 0..1 p/ a SpacePolicy (0 = mesma zona; 1 = paredes no caminho)
    same_zone: bool     # ouvinte e fonte no mesmo cômodo?
    hops: int           # nº de "paredes"/portas entre as zonas (0 = mesma; -1 = sem caminho)
    damping: float = 0.0  # absorção do cômodo do OUVINTE (0..1); alto = seco (mobiliado)


@dataclass
class SceneModel:
    """Grafo de zonas + onde cada fonte está + por onde o ouvinte anda.

    `source_zone[event_id]`  = zona da FONTE daquele evento (fala/SFX).
    `listener_zone[event_id]`= zona do OUVINTE quando aquele evento toca (o POV pode
    mudar de cômodo ao longo da cena — é o que faz o reverb "seguir" o personagem).
    Ausência de chave cai no `default_zone`. Sem zona nenhuma → tudo no default (seco)."""

    zones: dict[str, Zone] = field(default_factory=dict)
    adjacency: set[frozenset[str]] = field(default_factory=set)
    source_zone: dict[str, str] = field(default_factory=dict)
    listener_zone: dict[str, str] = field(default_factory=dict)
    default_zone: str = ""

    # ------------------------------------------------------------------ #
    def add_zone(self, zone: Zone) -> "SceneModel":
        self.zones[zone.id] = zone
        if not self.default_zone:
            self.default_zone = zone.id
        return self

    def link(self, a: str, b: str) -> "SceneModel":
        """Conecta duas zonas (uma porta/passagem). Sela adjacência simétrica."""
        if a != b:
            self.adjacency.add(frozenset((a, b)))
        return self

    def place_source(self, event_id: str, zone_id: str) -> "SceneModel":
        self.source_zone[event_id] = zone_id
        return self

    def move_listener(self, event_id: str, zone_id: str) -> "SceneModel":
        self.listener_zone[event_id] = zone_id
        return self

    # ------------------------------------------------------------------ #
    def _zone_of_listener(self, event_id: str) -> str:
        return self.listener_zone.get(event_id, self.default_zone)

    def _zone_of_source(self, event_id: str) -> str:
        # fonte sem zona explícita assume a zona do ouvinte (está "no mesmo cômodo").
        return self.source_zone.get(event_id, self._zone_of_listener(event_id))

    def hops(self, a: str, b: str) -> int:
        """Menor nº de paredes/portas entre duas zonas (BFS no grafo de adjacência).
        0 = mesma zona; 1 = cômodos vizinhos (uma porta); -1 = sem caminho conhecido."""
        if a == b:
            return 0
        if not a or not b:
            return -1
        seen = {a}
        queue: deque[tuple[str, int]] = deque([(a, 0)])
        while queue:
            node, dist = queue.popleft()
            for pair in self.adjacency:
                if node in pair:
                    other = next(iter(pair - {node}), node)
                    if other == b:
                        return dist + 1
                    if other not in seen:
                        seen.add(other)
                        queue.append((other, dist + 1))
        return -1

    def cue(self, event_id: str) -> SpatialCue:
        """Resolve a acústica espacial de um evento a partir do modelo."""
        lz = self._zone_of_listener(event_id)
        sz = self._zone_of_source(event_id)
        zone = self.zones.get(lz)
        space = zone.space if zone else self.default_zone_space()
        damping = zone.effective_damping if zone else default_damping(space)
        hops = self.hops(lz, sz)

        if hops == 0:
            return SpatialCue(space=space, distance="media", occlusion=0.0,
                              same_zone=True, hops=0, damping=damping)
        if hops == 1:
            # cômodo vizinho: parte do som vem pela porta, mas a parede come os agudos.
            return SpatialCue(space=space, distance="longe", occlusion=0.55,
                              same_zone=False, hops=1, damping=damping)
        # 2+ paredes OU sem caminho: bem abafado e distante.
        return SpatialCue(space=space, distance="muito_longe", occlusion=0.9,
                          same_zone=False, hops=hops, damping=damping)

    def default_zone_space(self) -> str:
        z = self.zones.get(self.default_zone)
        return z.space if z else "seco"

    def is_trivial(self) -> bool:
        """True se o modelo não separa nada (0 ou 1 zona): espacializar não muda nada."""
        return len(self.zones) <= 1

    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        """Forma serializável (o Screenwriter emite; o pipeline reconstrói)."""
        return {
            "zonas": [{"id": z.id, "space": z.space, "nome": z.name,
                       "damping": z.effective_damping}
                      for z in self.zones.values()],
            "ligacoes": [sorted(pair) for pair in self.adjacency],
            "fontes": dict(self.source_zone),
            "ouvinte": dict(self.listener_zone),
            "zona_padrao": self.default_zone,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "SceneModel":
        d = d or {}
        model = cls()
        for z in d.get("zonas", []):
            damp = z.get("damping")
            model.zones[str(z["id"])] = Zone(
                id=str(z["id"]), space=str(z.get("space", "seco")),
                name=str(z.get("nome", z.get("name", ""))),
                damping=(float(damp) if damp is not None else None))
        for pair in d.get("ligacoes", []):
            if len(pair) == 2:
                model.link(str(pair[0]), str(pair[1]))
        model.source_zone = {str(k): str(v) for k, v in d.get("fontes", {}).items()}
        model.listener_zone = {str(k): str(v) for k, v in d.get("ouvinte", {}).items()}
        model.default_zone = str(d.get("zona_padrao", d.get("default_zone", "")))
        if not model.default_zone and model.zones:
            model.default_zone = next(iter(model.zones))
        return model
