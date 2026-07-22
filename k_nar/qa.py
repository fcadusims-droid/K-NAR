"""QA acústico automatizado — a rede de segurança antes de multiplicar camadas.

Duas famílias de checagem, ambas de DADO PURO (stdlib), para rodarem no CI sem
numpy/áudio:

* `check_timeline(timeline)` — inspeciona a EDL: sobreposições que ENGOLEM palavras,
  cortes de interrupção agressivos demais (abaixo do mínimo audível), e falas que se
  cruzam sem que a intenção (sobreposição/interrupção) explique.
* `check_mix(stats)` — recebe as estatísticas de pico/clipping já medidas pelo DSP
  (`render.dsp.clipping_stats`) e sinaliza clipping/pico perigoso.

É a formalização do utilitário `Timeline.overlaps()`: em vez de só listar, classifica
e dá um veredito acionável. Antes das camadas narrativas (narração + SFX + ambiência),
o QA vira o portão que impede o áudio de degradar silenciosamente.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class QAIssue:
    """Um achado de QA. `severity` ∈ {"info","warn","error"}."""

    severity: str
    code: str
    message: str
    event_ids: tuple[str, ...] = ()

    def __str__(self) -> str:
        who = f" [{', '.join(self.event_ids)}]" if self.event_ids else ""
        return f"{self.severity.upper()} {self.code}: {self.message}{who}"


# Frações de referência (poderiam virar campos de política se precisar afinar).
_SWALLOW_FRACTION = 0.85   # sobreposição que cobre >85% da fala mais curta = engolida
_CLIP_CEILING = 0.999      # |amostra| >= isto conta como clipada
# As checagens de sobreposição valem só entre FALAS: SFX e ambiência coexistem com
# a fala DE PROPÓSITO (o ducking cuida do nível), então não são "cruzamento".
_SPEECH_TRACKS = ("dialogo", "narracao")


def check_timeline(timeline, policy=None) -> list[QAIssue]:
    """Achados de QA sobre a EDL (sem áudio). Ordenados por severidade."""
    issues: list[QAIssue] = []
    min_audible = getattr(policy, "min_audible_ms", 400)

    # 1) Corte de interrupção agressivo demais: sobra menos que o mínimo audível.
    for p in timeline.placements:
        if p.hard_cut_ms is None:
            continue
        audible = p.end_ms - p.start_ms
        if audible < min_audible:
            issues.append(QAIssue(
                "warn", "corte_agressivo",
                f"corte deixa só {audible}ms audíveis (< mínimo {min_audible}ms)",
                (p.event_id,)))

    # 2) Sobreposições ENTRE FALAS: engolir palavras e cruzamentos não-intencionais.
    #    (SFX/ambiência coexistem com a fala de propósito — o ducking resolve o nível.)
    ordered = sorted((p for p in timeline.placements if p.track in _SPEECH_TRACKS),
                     key=lambda p: p.start_ms)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if b.start_ms >= a.natural_end_ms:
                break  # ordenado por início: nada depois cruza A
            # tempo em que A (audível, respeitando corte) e B coexistem de fato
            overlap = min(a.end_ms, b.natural_end_ms) - max(a.start_ms, b.start_ms)
            if overlap <= 0:
                continue

            entry = b.entry_type
            if entry == "sequencial":
                # uma fala sequencial NÃO deveria cruzar a anterior — bug de timing.
                issues.append(QAIssue(
                    "error", "cruzamento_inesperado",
                    f"fala sequencial cruza a anterior por {overlap}ms",
                    (a.event_id, b.event_id)))
                continue

            # sobreposição/interrupção são intencionais; o risco é ENGOLIR a mais curta
            shorter = min(a.end_ms - a.start_ms, b.natural_end_ms - b.start_ms)
            if shorter > 0 and overlap / shorter > _SWALLOW_FRACTION:
                issues.append(QAIssue(
                    "warn", "fala_engolida",
                    f"sobreposição cobre {overlap/shorter:.0%} da fala mais curta "
                    f"({overlap}ms) — risco de ininteligibilidade",
                    (a.event_id, b.event_id)))

    order = {"error": 0, "warn": 1, "info": 2}
    return sorted(issues, key=lambda x: order.get(x.severity, 3))


def check_mix(stats: dict) -> list[QAIssue]:
    """Achados sobre a mixagem final, a partir das estatísticas medidas pelo DSP."""
    issues: list[QAIssue] = []
    peak = float(stats.get("peak", 0.0))
    clipped = int(stats.get("clipped_samples", 0))
    ratio = float(stats.get("clipped_ratio", 0.0))
    if clipped > 0:
        issues.append(QAIssue(
            "error", "clipping",
            f"{clipped} amostras clipadas ({ratio:.4%}) — pico {peak:.3f} no teto"))
    elif peak >= 0.98:
        issues.append(QAIssue(
            "warn", "pico_alto",
            f"pico {peak:.3f} muito perto do teto (headroom < 0.2 dB)"))
    return issues


def format_report(issues: list[QAIssue]) -> str:
    """Relatório legível; string vazia (na prática 'ok') quando não há achados."""
    if not issues:
        return "QA: nenhum problema detectado."
    lines = [f"QA: {len(issues)} achado(s)"]
    lines += [f"  - {iss}" for iss in issues]
    return "\n".join(lines)
