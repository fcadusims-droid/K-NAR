"""ProximityPolicy — a matriz DISTÂNCIA → acústica (no espírito do TimingPolicy).

Um som "ao longe" não é só mais baixo: o ar come os agudos (fica abafado) e ele soa
mais central/estreito no estéreo. Um som "à queima-roupa" é o oposto — alto, brilhante
e largo. Esta política traduz um rótulo de distância nesses três manipuladores:

    perto  →  +ganho, sem filtro, mais largo
    media  →  neutro
    longe  →  −ganho, passa-baixa (agudos somem), mais central
    muito_longe → bem baixo, bem abafado, quase mono

O Orquestrador resolve a distância e grava o resultado na EDL (ganho, pan e o corte
de passa-baixa); o renderer só APLICA — não adivinha.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Proximity:
    gain_db: float          # ajuste de nível relativo à distância "media"
    lowpass_hz: float       # corte do passa-baixa (0 = sem filtro)
    pan_scale: float        # <1 puxa o pan p/ o centro (longe), >1 alarga (perto)


@dataclass
class ProximityPolicy:
    levels: dict[str, Proximity] = field(default_factory=lambda: {
        "perto":       Proximity(gain_db=+3.0, lowpass_hz=0.0,    pan_scale=1.20),
        "media":       Proximity(gain_db=0.0,  lowpass_hz=0.0,    pan_scale=1.00),
        "longe":       Proximity(gain_db=-11.0, lowpass_hz=1800.0, pan_scale=0.45),
        "muito_longe": Proximity(gain_db=-18.0, lowpass_hz=1000.0, pan_scale=0.25),
    })

    # apelidos aceitos no rótulo de distância
    _aliases = {
        "proximo": "perto", "próximo": "perto", "colado": "perto", "queima_roupa": "perto",
        "near": "perto", "close": "perto", "cerca": "perto",
        "media": "media", "médio": "media", "medio": "media", "normal": "media",
        "distante": "longe", "far": "longe", "lejos": "longe", "afastado": "longe",
        "muito_distante": "muito_longe", "faraway": "muito_longe", "remoto": "muito_longe",
    }

    def resolve(self, distance: str) -> Proximity:
        key = str(distance or "media").strip().lower()
        key = self._aliases.get(key, key)
        return self.levels.get(key, self.levels["media"])
