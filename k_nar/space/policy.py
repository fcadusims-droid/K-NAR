"""SpacePolicy — a matriz OCLUSÃO → acústica (no espírito da ProximityPolicy).

Quando uma fonte está atrás de uma parede (noutra zona), a parede age como um
passa-baixa físico: come os agudos e derruba o nível. É o "som que bate na parede e
volta" — o que dá a sensação de que a voz vem do cômodo ao lado, não do seu ouvido.

A oclusão (0..1) vem do `SceneModel` (0 = mesma zona; ~0.55 = cômodo vizinho por uma
porta; ~0.9 = paredes no caminho). Esta política a traduz em dois manipuladores que o
renderer já aplica: um corte de passa-baixa e uma atenuação em dB. O Orquestrador
resolve e grava na EDL; o renderer só aplica.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SpacePolicy:
    # Corte de passa-baixa em oclusão TOTAL (parede densa): só passa o "corpo" grave.
    wall_lowpass_hz: float = 850.0
    # Corte de referência com oclusão mínima audível (som quase aberto, pela fresta).
    open_lowpass_hz: float = 3500.0
    # Atenuação (dB) em oclusão total — a parede também derruba o nível.
    wall_gain_db: float = -9.0

    def resolve(self, occlusion: float) -> tuple[float, float]:
        """(lowpass_hz, gain_db) para uma oclusão 0..1.

        occlusion<=0 → sem filtro nem atenuação (mesma zona; caminho livre).
        Interpola o corte de `open_lowpass_hz` (pouca oclusão) até `wall_lowpass_hz`
        (parede cheia) e a atenuação linearmente até `wall_gain_db`."""
        occ = max(0.0, min(1.0, float(occlusion)))
        if occ <= 0.0:
            return 0.0, 0.0
        lowpass = self.open_lowpass_hz + occ * (self.wall_lowpass_hz - self.open_lowpass_hz)
        gain_db = occ * self.wall_gain_db
        return lowpass, gain_db
