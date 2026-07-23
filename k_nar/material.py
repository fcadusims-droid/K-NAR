"""MaterialPolicy — a matriz MATERIAL → acústica (no espírito da ProximityPolicy).

Um passo de bota em assoalho de madeira não soa como um chinelo em concreto: muda o
**timbre** (madeira é quente, concreto é duro e brilhante, tapete é abafado) e o
**nível** (bota soca, chinelo é discreto). Isso vale para qualquer foley, não só
passos — uma pancada numa porta de metal ≠ numa de madeira.

Esta política traduz os materiais mencionados na frase (superfície + calçado) em dois
manipuladores que o renderer já aplica: um ajuste de ganho (dB) e um corte de
passa-baixa (materiais macios comem os agudos). Os efeitos SOMAM (bota + madeira) e
são capados. O Screenwriter detecta as palavras; o Orquestrador grava na EDL.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MaterialPolicy:
    # material (superfície ou calçado, chave canônica) → (ganho_db, lowpass_hz).
    # lowpass 0 = sem filtro (material duro/brilhante). Materiais macios abafam.
    levels: dict[str, tuple[float, float]] = field(default_factory=lambda: {
        # superfícies DURAS / brilhantes (som seco e alto)
        "concreto": (+1.0, 0.0), "pedra": (+1.0, 0.0), "metal": (+1.5, 0.0),
        "azulejo": (+1.0, 0.0), "ceramica": (+0.5, 0.0), "vidro": (+1.0, 0.0),
        # superfícies MÉDIAS / quentes
        "madeira": (0.0, 6500.0), "cascalho": (0.0, 7000.0),
        # superfícies MACIAS / abafadas (baixas, sem agudos)
        "grama": (-3.0, 3200.0), "terra": (-2.5, 3500.0), "folhas": (-2.0, 4000.0),
        "tapete": (-5.0, 2600.0), "carpete": (-5.0, 2600.0), "neve": (-3.0, 4200.0),
        "areia": (-3.0, 3200.0), "lama": (-3.5, 2800.0),
        # CALÇADO
        "bota": (+2.0, 0.0), "salto": (+1.5, 0.0), "tenis": (-1.0, 6000.0),
        "chinelo": (-3.0, 4000.0), "sandalia": (-2.0, 4500.0),
        "descalco": (-4.0, 3500.0), "meia": (-4.5, 3000.0),
    })
    max_gain_db: float = 3.0
    min_gain_db: float = -8.0

    def resolve(self, material: str) -> tuple[float, float]:
        """(ganho_db, lowpass_hz) dos materiais na frase (palavras separadas por espaço).
        Ganhos somam; o passa-baixa fica no mais restritivo (o material mais abafado)."""
        gain = 0.0
        lowpass = 0.0
        for word in str(material or "").split():
            hit = self.levels.get(word)
            if not hit:
                continue
            dg, dlp = hit
            gain += dg
            if dlp > 0:
                lowpass = dlp if lowpass <= 0 else min(lowpass, dlp)
        gain = max(self.min_gain_db, min(self.max_gain_db, gain))
        return gain, lowpass
