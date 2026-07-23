"""O Orquestrador de Duas Passagens — o motor que resolve a dependência circular.

    PASSAGEM 1 (fora daqui): o LLM cospe texto + metadados RELATIVOS.
    PASSAGEM 2 (aqui): sintetiza cada fala "seca" e MEDE a duração real.
    PASSAGEM 3 (aqui): cruza metadado relativo x duração real -> Timeline (EDL).

O Orquestrador é agnóstico de TTS (depende só do Protocol `TTSBackend`) e não
produz áudio: devolve uma `Timeline` de dados puros, que o DSP renderiza depois.
"""

from __future__ import annotations

from k_nar.emotion import EmotionPolicy
from k_nar.material import MaterialPolicy
from k_nar.models import EntryType, Scene, Track
from k_nar.prosody import ProsodyPolicy
from k_nar.proximity import ProximityPolicy
from k_nar.space import SceneModel, SpacePolicy
from k_nar.timeline import Placement, Timeline, TimingPolicy
from k_nar.tts.base import RenderedClip, TTSBackend

_SPEECH_TRACKS = {Track.DIALOGUE.value, Track.NARRATION.value}


def _track_of(ev) -> str:
    """Nome da trilha de um evento (aceita Enum Track ou string)."""
    t = getattr(ev, "track", None)
    return getattr(t, "value", t) or "dialogo"


class Orquestrador:
    def __init__(self, tts: TTSBackend, policy: TimingPolicy | None = None,
                 prosody: ProsodyPolicy | None = None,
                 proximity: ProximityPolicy | None = None,
                 scene_model: SceneModel | None = None,
                 space_policy: SpacePolicy | None = None,
                 spatial_narration: bool = False,
                 material: MaterialPolicy | None = None,
                 scene_damping: float = 0.0):
        self.tts = tts
        self.policy = policy or TimingPolicy()
        # mesma matriz de prosódia do backend neural: o ganho de dinâmica na EDL
        # fica consistente com o pitch/rate que o TTS já aplicou na onda.
        self.prosody = prosody or ProsodyPolicy()
        # matriz distância → acústica (nível/abafamento/largura) dos SFX.
        self.proximity = proximity or ProximityPolicy()
        # matriz material → timbre/nível dos SFX (bota em madeira ≠ chinelo em concreto).
        self.material = material or MaterialPolicy()
        # amortecimento global (mobília/uso) do reverb não-espacial da cena.
        self.scene_damping = scene_damping
        # matriz de atuação: resolve as micro-pausas emocionais (respiro antes/depois).
        self.emotion = EmotionPolicy()
        # Nível 1 (modo espacial, OPCIONAL): o "set virtual" de zonas. Quando dado (e
        # não-trivial), a acústica de cada evento é DERIVADA do modelo — reverb do
        # cômodo do ouvinte + oclusão da parede + distância — em vez de rótulos à mão.
        self.scene_model = scene_model
        self.space = space_policy or SpacePolicy()
        # Em 1ª pessoa a narração É o protagonista, DENTRO da cena: leva o reverb do
        # cômodo (espacializada). Em 3ª pessoa o narrador é onisciente (seco) e fica de
        # fora do palco. Este flag liga a narração no palco espacial.
        self.spatial_narration = spatial_narration

    @property
    def _spatial(self) -> bool:
        return self.scene_model is not None and not self.scene_model.is_trivial()

    def _spatial_tracks(self) -> tuple[str, ...]:
        base = (Track.DIALOGUE.value, Track.SFX.value)
        return base + (Track.NARRATION.value,) if self.spatial_narration else base

    # ------------------------------------------------------------------ #
    def render_scene(self, scene: Scene,
                     clips: dict[str, RenderedClip] | None = None) -> Timeline:
        """Roda as passagens 2 e 3 e devolve a linha de tempo da cena.

        `clips` pode ser pré-fornecido (ex.: sintetizado em paralelo/cache via
        `tts.batch.synthesize_all`), evitando que a passagem 2 lenta bloqueie o
        fluxo. Se omitido, sintetiza serialmente (comportamento padrão).
        """
        # Ambiência é uma CAMA (bed): não entra na sequência temporal (é localizada
        # por âncoras depois). Separa-se dos eventos sequenciáveis (fala + SFX pontual).
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
            # ATUAÇÃO (Fase B2): um respiro ANTES de uma fala carregada (suspense/medo)
            # — só em entrada sequencial (não atrapalha interrupção/sobreposição).
            pause_before, pause_after = self._emotion_pauses(ev)
            if etype == EntryType.SEQUENTIAL:
                start_ms += pause_before

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

            # Acústica ESPACIAL (Nível 1): quando há um "set virtual" de zonas, a
            # distância/abafamento/reverb saem do modelo (cômodo do ouvinte × cômodo da
            # fonte) — para o diálogo e o SFX (e a narração, só em 1ª pessoa, quando ela
            # É o protagonista dentro da cena). O narrador ONISCIENTE (3ª pessoa) fica de
            # fora do palco. Sem modelo: distância só do rótulo do SFX (modo clássico).
            if self._spatial and cur_track in self._spatial_tracks():
                self._apply_spatial(placement, ev, cur_track)
            elif cur_track == Track.SFX.value:
                self._apply_proximity(placement, getattr(ev, "distance", "media"))

            # MATERIAL do foley (independe de espaço): bota em madeira ≠ chinelo em
            # concreto — ajusta timbre (passa-baixa) e nível. Só SFX.
            if cur_track == Track.SFX.value:
                self._apply_material(placement, ev)

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

            # Avança o cursor: fim EFETIVO deste evento + pausa dramática de saída +
            # o silêncio emocional DEPOIS (tristeza/cansaço deixam a frase "assentar").
            pause = self.policy.pause_ms(ev.exit) + pause_after
            cursor_ms = placement.natural_end_ms + pause
            prev = placement
            prev_clip = clip

        total = max((p.natural_end_ms for p in placements), default=0)

        # Ambiência LOCALIZADA: cada cama entra quando o elemento é mencionado (start_id)
        # e sai na última menção + cauda (end_id + tail), com fades — não toca a cena
        # inteira nem "acaba do nada". Sem âncoras (retrocompat): cobre [0, total].
        id_times = {p.event_id: (p.start_ms, p.natural_end_ms) for p in placements}
        for amb in ambience:
            start_id = getattr(amb, "start_id", "")
            end_id = getattr(amb, "end_id", "")
            start_ms = id_times[start_id][0] if start_id in id_times else 0
            end_ms = (id_times[end_id][1] + self.policy.ambience_tail_ms
                      if end_id in id_times else total)
            end_ms = min(end_ms, total)                # não passa do fim da cena
            dur = max(0, end_ms - start_ms)
            placements.append(Placement(
                event_id=amb.id, character="", start_ms=start_ms, duration_ms=dur,
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
            damping=self.scene_damping,   # mobília/uso do espaço único (não-espacial)
        )

    # ------------------------------------------------------------------ #
    _DIST_ORDER = ("perto", "media", "longe", "muito_longe")

    def _apply_proximity(self, p: Placement, distance: str) -> None:
        """Grava na EDL a acústica da distância: ganho, pan (mais central quando longe)
        e o corte de passa-baixa (abafamento). O renderer só aplica."""
        prox = self.proximity.resolve(distance)
        p.distance = self.proximity.canonical(distance)
        p.gain_db += prox.gain_db
        p.pan = int(max(-100, min(100, round(p.pan * prox.pan_scale))))
        p.lowpass_hz = prox.lowpass_hz

    def _apply_material(self, p: Placement, ev) -> None:
        """Timbre + nível do material do foley: bota soca e é grave; chinelo/tapete
        abafam e somem. Soma ao ganho e combina o passa-baixa (o mais restritivo)."""
        material = getattr(ev, "material", "")
        if not material:
            return
        gain_db, lowpass = self.material.resolve(material)
        p.gain_db += gain_db
        p.material = material
        if lowpass > 0:
            p.lowpass_hz = lowpass if p.lowpass_hz <= 0 else min(p.lowpass_hz, lowpass)

    def _apply_spatial(self, p: Placement, ev, track: str) -> None:
        """Deriva a acústica do evento do `SceneModel`: o reverb do cômodo do OUVINTE,
        a distância (mesma zona × outra) e a OCLUSÃO (a parede abafa e derruba o nível —
        é o som que "vem do cômodo ao lado"). Tudo vira dado na EDL; o renderer aplica."""
        cue = self.scene_model.cue(ev.id)
        if cue.space and cue.space != "seco":
            p.space = cue.space
            p.damping = cue.damping   # cômodo mobiliado/em uso → seco; vazio → eco
        # distância: a MAIS distante entre a do modelo e a do próprio SFX ("ao longe"),
        # para o rótulo do autor e a perspectiva de cômodo não se cancelarem.
        distance = cue.distance
        if track == Track.SFX.value:
            distance = self._farther(distance, getattr(ev, "distance", "media"))
        self._apply_proximity(p, distance)
        # oclusão: soma o abafamento/atenuação da parede ao que a distância já fez.
        lp, gain_db = self.space.resolve(cue.occlusion)
        if lp > 0:
            p.lowpass_hz = lp if p.lowpass_hz <= 0 else min(p.lowpass_hz, lp)
        p.gain_db += gain_db

    def _farther(self, a: str, b: str) -> str:
        ca, cb = self.proximity.canonical(a), self.proximity.canonical(b)
        ia = self._DIST_ORDER.index(ca) if ca in self._DIST_ORDER else 1
        ib = self._DIST_ORDER.index(cb) if cb in self._DIST_ORDER else 1
        return ca if ia >= ib else cb

    def _emotion_pauses(self, ev) -> tuple[int, int]:
        """(pausa_antes, pausa_depois) em ms da emoção da fala — o respiro dramático.
        Só para eventos de fala (com `.voice`); SFX/ambiência não têm."""
        voice = getattr(ev, "voice", None)
        if voice is None:
            return 0, 0
        shift = self.emotion.resolve(getattr(voice, "emotion", "neutro"),
                                     getattr(voice, "intensity", 0.0))
        return shift.pause_before_ms, shift.pause_after_ms

    def _gain_of(self, ev) -> float:
        """Ganho de dinâmica do evento: por tensão + EMOÇÃO (fala, coerente c/ o TTS) ou
        o ganho fixo do próprio evento (SFX)."""
        if hasattr(ev, "voice"):
            return self.prosody.resolve(
                ProsodyPolicy.tension_scalar(ev.voice.tension),
                emotion=getattr(ev.voice, "emotion", "neutro"),
                intensity=getattr(ev.voice, "intensity", 0.0)).gain_db
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
