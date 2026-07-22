"""MixPolicy — o "diretor de mix": o balanço entre as camadas num objeto só.

No espírito do `TimingPolicy` (ritmo) e do `ProsodyPolicy` (expressividade): TODO
número do balanço de mixagem vive aqui. Afinar o "som" do audiodrama inteiro — a
fala mais alta, a ambiência mais discreta, a música bem ao fundo — é ajustar UM
objeto. Um `MixPolicy` diferente = um "estilo de mixagem".

Dois níveis, de propósito:
  * ganho por EVENTO (o Director/Screenwriter decide: tensão da fala, força do tiro);
  * trim de BUS por trilha (o mixador decide aqui: o balanço geral entre as camadas).

E a profundidade do DUCKING (quanto ambiência/SFX/música afundam sob a fala), com as
listas de quem é a "chave" (a fala manda) e quem afunda.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MixPolicy:
    """A matriz de balanço de mixagem. Um objeto = um estilo de mixagem."""

    # Trim de bus por trilha (dB). Aplicado ao bed inteiro de cada trilha, por cima
    # do ganho por evento. Diálogo é a referência (0); o resto se posiciona ao redor.
    track_level_db: dict[str, float] = field(default_factory=lambda: {
        "dialogo": 0.0,
        "narracao": -1.0,     # narrador um tico atrás do diálogo
        "sfx": -2.0,          # efeitos presentes, mas sem competir com a fala
        "ambiencia": 0.0,     # a cama já entra baixa pelo ganho do evento (~-20 dB)
        "musica": -6.0,       # trilha bem ao fundo
    })

    # Profundidade do ducking: quanto as trilhas duckadas afundam sob a fala plena.
    duck_db: float = -12.0

    # Quem é a CHAVE (a presença dispara o ducking) e quem AFUNDA sob ela.
    key_tracks: tuple[str, ...] = ("dialogo", "narracao")
    ducked_tracks: tuple[str, ...] = ("ambiencia", "sfx", "musica")

    # ------------------------------------------------------------------ #
    def level_gain(self, track: str) -> float:
        """Fator linear do trim de bus da trilha (10^(dB/20))."""
        return 10.0 ** (self.track_level_db.get(track, 0.0) / 20.0)
