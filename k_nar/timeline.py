"""A MATRIZ de tradução (TimingPolicy) + as estruturas da linha de tempo.

Aqui mora TODO número mágico do ritmo dramático. O LLM manda intenção relativa
("agressividade 0.25", "pausa curta"); esta matriz cruza isso com a duração REAL
medida pelo TTS e devolve milissegundos. Afinar o "feeling" do drama inteiro =
mexer só neste arquivo.

Ponto-chave que valida a tese da conversa: a mesma `agressividade=0.25` produz
cortes diferentes conforme a fala anterior dura 2s ou 4s. O peso emocional (0.25)
vem do Diretor/LLM; a matemática dos milissegundos é resolvida aqui.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from k_nar.models import DramaticPause, ExitDynamics


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class TimingPolicy:
    """A matriz relativo -> milissegundos. Um objeto = um "estilo de direção"."""

    # Pausa dramática (silêncio após a fala) -> ms.
    dramatic_pause_ms: dict[DramaticPause, int] = field(
        default_factory=lambda: {
            DramaticPause.NONE: 0,
            DramaticPause.SHORT: 200,
            DramaticPause.MEDIUM: 550,
            DramaticPause.LONG: 1100,
        }
    )

    # Rótulos qualitativos de tensão -> escalar 0..1 (usado pelo TTS, resolvido aqui).
    tension_labels: dict[str, float] = field(
        default_factory=lambda: {
            "baixa": 0.15,
            "media": 0.50,
            "alta": 0.80,
            "extrema": 1.00,
        }
    )

    # --- Guardas de inteligibilidade (o item "QA" que impede engolir a fala) ---
    # Uma interrupção nunca corta antes de o anterior tocar ao menos esta fração...
    min_audible_fraction: float = 0.35
    # ...nem antes deste tempo absoluto (protege falas curtas).
    min_audible_ms: int = 400
    # Teto de agressividade: mesmo "brutal", sempre sobra um respiro.
    max_aggressiveness: float = 0.90

    # Sobreposição (fala simultânea) costuma entrar mais cedo que interrupção,
    # mas sem a guarda dura — as vozes coexistem, então pode invadir mais.
    overlap_min_audible_fraction: float = 0.15

    # --- Envelopes de atenuação (a EDL carrega isto; o renderer NÃO adivinha) ---
    # Micro-fades nas bordas de toda fala: matam o clique digital de descontinuidade.
    edge_fade_in_ms: int = 8
    edge_fade_out_ms: int = 12
    # Fade do CORTE de interrupção: rápido, mas suave o bastante p/ não estalar.
    interruption_fade_ms: int = 32
    # A fala que ENTRA interrompendo sobe por cima da cauda da anterior ("swell").
    interruption_swell_in_ms: int = 45
    # Tolerância que o renderer tem p/ deslizar o corte até um vale de energia
    # (silêncio/valão) e não decepar no meio de uma consoante plosiva.
    # É a resposta pragmática ao "forced alignment": corte proporcional escolhido
    # pelo Orquestrador + ajuste fino acústico dentro desta janela.
    cut_snap_window_ms: int = 55

    # ------------------------------------------------------------------ #
    #  Traduções relativo -> real                                        #
    # ------------------------------------------------------------------ #
    def pause_ms(self, exit: ExitDynamics) -> int:
        """Silêncio (ms) a inserir depois de uma fala."""
        return self.dramatic_pause_ms.get(exit.dramatic_pause, 0)

    def resolve_tension(self, value) -> float:
        """Aceita número (0..1) OU rótulo ("alta") e devolve escalar 0..1."""
        if isinstance(value, (int, float)):
            return _clamp(float(value), 0.0, 1.0)
        return self.tension_labels.get(str(value).strip().lower(), 0.0)

    def interruption_start_within_prev(self, prev_duration_ms: int, aggressiveness: float) -> int:
        """Onde a interrupção entra, em ms a partir do INÍCIO da fala anterior.

        aggressiveness=0.25 => corta os últimos 25% => entra em 75% do anterior.
        As guardas garantem que o anterior sempre seja audível o suficiente.
        """
        agg = _clamp(aggressiveness, 0.0, self.max_aggressiveness)
        natural_start = prev_duration_ms * (1.0 - agg)
        floor = max(self.min_audible_ms, int(prev_duration_ms * self.min_audible_fraction))
        floor = min(floor, prev_duration_ms)  # nunca ultrapassa o fim do anterior
        return int(max(natural_start, floor))

    def overlap_start_within_prev(self, prev_duration_ms: int, aggressiveness: float) -> int:
        """Igual à interrupção, mas com guarda mais frouxa: na fala simultânea
        ninguém é cortado, então uma voz pode invadir mais cedo a outra."""
        agg = _clamp(aggressiveness, 0.0, 1.0)
        natural_start = prev_duration_ms * (1.0 - agg)
        floor = int(prev_duration_ms * self.overlap_min_audible_fraction)
        return int(max(natural_start, floor))


@dataclass
class Placement:
    """Uma fala já ANCORADA no tempo. Item da Edit Decision List (EDL)."""

    event_id: str
    character: str
    start_ms: int
    duration_ms: int
    pan: int
    text: str
    # Se esta fala foi interrompida, o renderer deve cortar/duckar aqui (ms absolutos).
    # None = toca inteira. É a diferença concreta entre interrupção e sobreposição.
    hard_cut_ms: int | None = None
    # Envelopes de atenuação decididos pelo Orquestrador (não pelo renderer):
    fade_in_ms: int = 0        # micro-fade de entrada (anti-clique) ou "swell" de interrupção
    fade_out_ms: int = 0       # micro-fade de saída, OU o fade do corte se interrompida
    # Tolerância (ms) que o renderer pode deslizar o corte até um vale de energia.
    cut_snap_window_ms: int = 0

    @property
    def end_ms(self) -> int:
        """Fim EFETIVO: respeita o corte de interrupção, se houver."""
        if self.hard_cut_ms is not None:
            return self.hard_cut_ms
        return self.start_ms + self.duration_ms

    @property
    def natural_end_ms(self) -> int:
        """Fim se a fala tocasse inteira, ignorando corte."""
        return self.start_ms + self.duration_ms


@dataclass
class Timeline:
    """Saída da PASSAGEM 3: pura estrutura de dados (EDL). Nenhum byte de áudio.
    O DSP/render (pedalboard, pydub) consome isto depois."""

    scene_id: str
    ambiance: str
    placements: list[Placement] = field(default_factory=list)
    total_duration_ms: int = 0

    def overlaps(self) -> list[tuple[str, str, int]]:
        """Utilitário de QA: pares (a, b, ms_de_sobreposicao) que se cruzam no tempo.
        Útil para detectar automaticamente falas que engolem umas às outras."""
        result: list[tuple[str, str, int]] = []
        ordered = sorted(self.placements, key=lambda p: p.start_ms)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                if b.start_ms >= a.natural_end_ms:
                    break
                overlap = min(a.natural_end_ms, b.natural_end_ms) - b.start_ms
                if overlap > 0:
                    result.append((a.event_id, b.event_id, overlap))
        return result

    def to_dict(self) -> dict:
        return {
            "cena_id": self.scene_id,
            "ambientacao": self.ambiance,
            "duracao_total_ms": self.total_duration_ms,
            "trilha": [
                {
                    "id": p.event_id,
                    "personagem": p.character,
                    "inicio_ms": p.start_ms,
                    "duracao_ms": p.duration_ms,
                    "corte_ms": p.hard_cut_ms,
                    "estereo": p.pan,
                    "texto": p.text,
                }
                for p in self.placements
            ],
        }
