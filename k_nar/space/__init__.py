"""Nível 1 — o "set virtual" acústico: zonas (cômodos), adjacência e o POV que anda.

O `SceneModel` deriva a acústica de cada evento (reverb do cômodo do ouvinte,
distância e oclusão) de um GRAFO de zonas, em vez de rótulos escolhidos à mão. É
dado puro (stdlib); o Orquestrador grava o resultado na EDL e o renderer só aplica.
"""

from k_nar.space.model import SceneModel, SpatialCue, Zone
from k_nar.space.policy import SpacePolicy

__all__ = ["SceneModel", "SpatialCue", "Zone", "SpacePolicy"]
