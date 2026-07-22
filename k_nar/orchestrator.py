"""O Orquestrador de Duas Passagens — o motor que resolve a dependência circular.

    PASSAGEM 1 (fora daqui): o LLM cospe texto + metadados RELATIVOS.
    PASSAGEM 2 (aqui): sintetiza cada fala "seca" e MEDE a duração real.
    PASSAGEM 3 (aqui): cruza metadado relativo x duração real -> Timeline (EDL).

O Orquestrador é agnóstico de TTS (depende só do Protocol `TTSBackend`) e não
produz áudio: devolve uma `Timeline` de dados puros, que o DSP renderiza depois.
"""

from __future__ import annotations

from k_nar.models import EntryType, Scene, Track
from k_nar.prosody import ProsodyPolicy
from k_nar.timeline import Placement, Timeline, TimingPolicy
from k_nar.tts.base import RenderedClip, TTSBackend

_SPEECH_TRACKS = {Track.DIALOGUE.value, Track.NARRATION.value}


def _track_of(ev) -> str:
    """Nome da trilha de um evento (aceita Enum Track ou string)."""
    t = getattr(ev, "track", None)
    return getattr(t, "value", t) or "dialogo"


class Orquestrador:
    def __init__(self, tts: TTSBackend, policy: TimingPolicy | None = None,
                 prosody: ProsodyPolicy | None = None):
        self.tts = tts
        self.policy = policy or TimingPolicy()
        # mesma matriz de prosódia do backend neural: o ganho de dinâmica na EDL
        # fica consistente com o pitch/rate que o TTS já aplicou na onda.
        self.prosody = prosody or ProsodyPolicy()

    # ------------------------------------------------------------------ #
    def render_scene(self, scene: Scene,
                     clips: dict[str, RenderedClip] | None = None) -> Timeline:
        """Roda as passagens 2 e 3 e devolve a linha de tempo da cena.

        `clips` pode ser pré-fornecido (ex.: sintetizado em paralelo/cache via
        `tts.batch.synthesize_all`), evitando que a passagem 2 lenta bloqueie o
        fluxo. Se omitido, sintetiza serialmente (comportamento padrão).
        """
        # Ambiência é uma CAMA (bed): cobre a cena inteira, não entra na sequência
        # temporal. Separa-se dos eventos sequenciáveis (fala + SFX pontual).
        sequenced = [ev for ev in scene.events if _track_of(ev) != Track.AMBIENCE.value]
        ambience = [ev for ev in scene.events if _track_of(ev) == Track.AMBIENCE.value]

        # PASSAGEM 2 — síntese/render "seco" + medição da duração REAL (só fala; SFX e
        # ambiência devem chegar em `clips`, renderizados pelo SfxBackend do chamador).
        if clips is None:
            clips = {ev.id: self.tts.synthesize(ev)
                     for ev in sequenced if _track_of(ev) in _SPEECH_TRACKS}

        # PASSAGEM 3 — alocação temporal dos eventos sequenciáveis.
        placements: list[Placement] = []
        cursor_ms = 0          # ponto onde o próximo evento começaria "naturalmente"
        prev: Placement | None = None
        prev_clip: RenderedClip | None = None

        for ev in sequenced:
            clip = clips.get(ev.id)
            if clip is None:
                continue  # sem áudio (ex.: SFX não renderizado): ignora silenciosamente
            cur_track = _track_of(ev)

            # Interrupção/sobreposição só valem DENTRO da mesma trilha: personagem
            # atropela personagem, mas ninguém interrompe o narrador (nem a narração
            # atropela o diálogo, nem um SFX corta a fala). Cruzou -> degrada p/ sequencial.
            etype = ev.entry.type
            if prev is not None and prev.track != cur_track and \
                    etype in (EntryType.INTERRUPTION, EntryType.OVERLAP):
                etype = EntryType.SEQUENTIAL

            start_ms = self._resolve_start(etype, ev.entry.aggressiveness, prev, cursor_ms)

            placement = Placement(
                event_id=ev.id,
                character=ev.character,
                start_ms=start_ms,
                duration_ms=clip.duration_ms,
                pan=ev.pan,
                text=ev.text or getattr(ev, "tag", ""),
                track=cur_track,
                # Bordas: micro-fades anti-clique em todo evento.
                fade_in_ms=self.policy.edge_fade_in_ms,
                fade_out_ms=self.policy.edge_fade_out_ms,
                entry_type=etype.value,
                gain_db=self._gain_of(ev),
            )

            # Interrupção: esta fala SOBE sobre a cauda da anterior ("swell") e
            # CORTA a anterior no ponto de entrada, com crossfade equal-power + snap.
            if prev is not None and etype == EntryType.INTERRUPTION:
                placement.fade_in_ms = self.policy.interruption_swell_in_ms
                placement.crossfade_ms = self.policy.crossfade_ms
                if start_ms < prev.natural_end_ms:
                    prev.fade_out_ms = self.policy.interruption_fade_ms
                    prev.crossfade_ms = self.policy.crossfade_ms
                    self._resolve_cut(prev, prev_clip, start_ms)

            # Sobreposição: a fala que entra também recebe swell equal-power curto.
            if prev is not None and etype == EntryType.OVERLAP:
                placement.crossfade_ms = self.policy.crossfade_ms

            placements.append(placement)

            # Avança o cursor: fim EFETIVO deste evento + pausa dramática de saída.
            pause = self.policy.pause_ms(ev.exit)
            cursor_ms = placement.natural_end_ms + pause
            prev = placement
            prev_clip = clip

        total = max((p.natural_end_ms for p in placements), default=0)

        # Ambiência: um placement por cama, cobrindo [0, total]. O renderer faz o
        # loop do sample até preencher; o ducking a faz afundar sob a fala.
        for amb in ambience:
            placements.append(Placement(
                event_id=amb.id, character="", start_ms=0, duration_ms=total,
                pan=0, text=getattr(amb, "tag", ""), track=Track.AMBIENCE.value,
                # fades longos: a cama entra/sai suave (não é um clique de borda).
                fade_in_ms=self.policy.ambience_fade_in_ms,
                fade_out_ms=self.policy.ambience_fade_out_ms,
                gain_db=getattr(amb, "gain_db", -20.0),
            ))

        return Timeline(
            scene_id=scene.id,
            ambiance=scene.ambiance,
            placements=placements,
            total_duration_ms=total,
        )

    # ------------------------------------------------------------------ #
    def _gain_of(self, ev) -> float:
        """Ganho de dinâmica do evento: por tensão (fala, coerente c/ o TTS) ou o
        ganho fixo do próprio evento (SFX)."""
        if hasattr(ev, "voice"):
            return self.prosody.resolve(ProsodyPolicy.tension_scalar(ev.voice.tension)).gain_db
        return float(getattr(ev, "gain_db", 0.0))

    # ------------------------------------------------------------------ #
    def _resolve_cut(self, prev: Placement, prev_clip: RenderedClip | None,
                     start_ms: int) -> None:
        """Decide ONDE cortar a fala interrompida `prev`.

        Se o clip anterior traz forced alignment (Piper), ancoramos o corte numa
        fronteira REAL de fonema/palavra próxima do ponto de entrada — a EDL passa
        a carregar a decisão e o renderer só aplica (cut_snap_window_ms=0).

        Sem alinhamento (mock/formante), delegamos ao renderer o snap de energia
        (fallback auditável): grava o alvo cru e a janela de tolerância na EDL.
        """
        alignment = getattr(prev_clip, "alignment", None) if prev_clip else None
        within_ms = start_ms - prev.start_ms  # ponto de corte relativo ao início do prev

        if alignment:
            sr = prev_clip.sample_rate
            target = round(within_ms / 1000 * sr)
            window = round(self.policy.cut_snap_window_ms / 1000 * sr)
            floor = min(round(self.policy.min_audible_ms / 1000 * sr), alignment.length)
            snapped, kind = alignment.snap(target, window=window, floor=floor)
            prev.hard_cut_ms = prev.start_ms + round(snapped / sr * 1000)
            # Ancoramos na fronteira LINGUÍSTICA; o renderer só refina dentro de uma
            # janela ESTREITA p/ o micro-vale acústico (fronteira vozeada != silêncio).
            prev.cut_snap_window_ms = self.policy.cut_refine_window_ms
            prev.cut_method = f"fonema:{kind}"
        else:
            # Sem alinhamento: alvo cru + janela LARGA p/ o renderer varrer o vale.
            prev.hard_cut_ms = start_ms
            prev.cut_snap_window_ms = self.policy.cut_snap_window_ms
            prev.cut_method = "energia"

    # ------------------------------------------------------------------ #
    def _resolve_start(self, etype: EntryType, aggressiveness: float,
                       prev: Placement | None, cursor_ms: int) -> int:
        """Traduz a dinâmica de entrada relativa em um ponto de início absoluto.

        Recebe o `etype` já resolvido (o laço degrada interrupção/sobreposição p/
        sequencial quando a fala cruza de trilha)."""
        if prev is None:
            return 0

        if etype == EntryType.SEQUENTIAL:
            # cursor_ms já inclui o fim do anterior + a pausa dramática dele.
            return cursor_ms

        if etype == EntryType.INTERRUPTION:
            within = self.policy.interruption_start_within_prev(
                prev.duration_ms, aggressiveness
            )
            return prev.start_ms + within

        if etype == EntryType.OVERLAP:
            within = self.policy.overlap_start_within_prev(
                prev.duration_ms, aggressiveness
            )
            return prev.start_ms + within

        return cursor_ms
