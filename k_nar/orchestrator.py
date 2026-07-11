"""O Orquestrador de Duas Passagens — o motor que resolve a dependência circular.

    PASSAGEM 1 (fora daqui): o LLM cospe texto + metadados RELATIVOS.
    PASSAGEM 2 (aqui): sintetiza cada fala "seca" e MEDE a duração real.
    PASSAGEM 3 (aqui): cruza metadado relativo x duração real -> Timeline (EDL).

O Orquestrador é agnóstico de TTS (depende só do Protocol `TTSBackend`) e não
produz áudio: devolve uma `Timeline` de dados puros, que o DSP renderiza depois.
"""

from __future__ import annotations

from k_nar.models import EntryType, Scene
from k_nar.timeline import Placement, Timeline, TimingPolicy
from k_nar.tts.base import RenderedClip, TTSBackend


class Orquestrador:
    def __init__(self, tts: TTSBackend, policy: TimingPolicy | None = None):
        self.tts = tts
        self.policy = policy or TimingPolicy()

    # ------------------------------------------------------------------ #
    def render_scene(self, scene: Scene) -> Timeline:
        """Roda as passagens 2 e 3 e devolve a linha de tempo da cena."""
        # PASSAGEM 2 — síntese "seca" + medição da duração REAL de cada fala.
        clips: dict[str, RenderedClip] = {
            ev.id: self.tts.synthesize(ev) for ev in scene.events
        }

        # PASSAGEM 3 — alocação temporal.
        placements: list[Placement] = []
        cursor_ms = 0          # ponto onde a próxima fala começaria "naturalmente"
        prev: Placement | None = None

        for ev in scene.events:
            clip = clips[ev.id]
            start_ms = self._resolve_start(ev, prev, cursor_ms)

            placement = Placement(
                event_id=ev.id,
                character=ev.character,
                start_ms=start_ms,
                duration_ms=clip.duration_ms,
                pan=ev.pan,
                text=ev.text,
                # Bordas: micro-fades anti-clique em toda fala.
                fade_in_ms=self.policy.edge_fade_in_ms,
                fade_out_ms=self.policy.edge_fade_out_ms,
            )

            # Interrupção: esta fala SOBE sobre a cauda da anterior ("swell") e
            # CORTA a anterior no ponto de entrada, com fade de corte + snap.
            if prev is not None and ev.entry.type == EntryType.INTERRUPTION:
                placement.fade_in_ms = self.policy.interruption_swell_in_ms
                if start_ms < prev.natural_end_ms:
                    prev.hard_cut_ms = start_ms
                    prev.fade_out_ms = self.policy.interruption_fade_ms
                    prev.cut_snap_window_ms = self.policy.cut_snap_window_ms

            placements.append(placement)

            # Avança o cursor: fim EFETIVO desta fala + pausa dramática de saída.
            pause = self.policy.pause_ms(ev.exit)
            cursor_ms = placement.natural_end_ms + pause
            prev = placement

        total = max((p.natural_end_ms for p in placements), default=0)
        return Timeline(
            scene_id=scene.id,
            ambiance=scene.ambiance,
            placements=placements,
            total_duration_ms=total,
        )

    # ------------------------------------------------------------------ #
    def _resolve_start(self, ev, prev: Placement | None, cursor_ms: int) -> int:
        """Traduz a dinâmica de entrada relativa em um ponto de início absoluto."""
        if prev is None:
            return 0

        etype = ev.entry.type
        if etype == EntryType.SEQUENTIAL:
            # cursor_ms já inclui o fim do anterior + a pausa dramática dele.
            return cursor_ms

        if etype == EntryType.INTERRUPTION:
            within = self.policy.interruption_start_within_prev(
                prev.duration_ms, ev.entry.aggressiveness
            )
            return prev.start_ms + within

        if etype == EntryType.OVERLAP:
            within = self.policy.overlap_start_within_prev(
                prev.duration_ms, ev.entry.aggressiveness
            )
            return prev.start_ms + within

        return cursor_ms
