"""Camada Narrative — a PASSAGEM 0 (prosa → roteiro estruturado).

Antecede a Camada Director: transforma a HISTÓRIA em prosa numa lista de elementos
(narração / diálogo / gatilhos de ação) que o Director então dirige (PASSAGEM 1).
"""

from k_nar.narrative.screenwriter import RuleBasedScreenwriter, Screenwriter

__all__ = ["RuleBasedScreenwriter", "Screenwriter"]
