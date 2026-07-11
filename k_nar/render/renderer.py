"""TimelineRenderer — consome a Timeline/EDL + clips de áudio e mixa a cena.

Dois modos, de propósito, para o A/B acústico:

* mode="naive": corta no `hard_cut_ms` frio, sem fade, sem snap, sem pan, sem
  reverb. Reproduz exatamente os problemas que a crítica previu — clique digital
  no corte e vozes num vácuo isolado.
* mode="full": aplica os envelopes que a EDL carrega (fades anti-clique), desliza
  o corte até o vale de energia (não decepa consoante), espalha no palco estéreo
  (pan equal-power) e passa TODAS as vozes pelo mesmo bus de reverb convolutivo
  (coesão acústica). Masteriza com pedalboard (passa-alta + limiter anti-clip).

O renderer só APLICA o que o Orquestrador decidiu — ele não inventa curvas.
"""

from __future__ import annotations

import numpy as np

from k_nar.render import dsp
from k_nar.render.impulse import make_impulse_response
from k_nar.timeline import Placement, Timeline
from k_nar.timeline import TimingPolicy

try:  # pedalboard é opcional; sem ele caímos num master por normalização de pico
    from pedalboard import HighpassFilter, Limiter, Pedalboard
    from pedalboard.io import AudioFile
    _HAS_PEDALBOARD = True
except Exception:  # pragma: no cover
    _HAS_PEDALBOARD = False


class TimelineRenderer:
    def __init__(self, sr: int = 24000, policy: TimingPolicy | None = None,
                 reverb_wet: float = 0.30):
        self.sr = sr
        self.policy = policy or TimingPolicy()
        self.reverb_wet = reverb_wet

    # ------------------------------------------------------------------ #
    def _ms(self, ms: float) -> int:
        return int(round(ms * self.sr / 1000.0))

    def render(self, timeline: Timeline, clips: dict[str, np.ndarray],
               mode: str = "full") -> np.ndarray:
        """Devolve a mixagem estéreo (2, N) float32."""
        ir = make_impulse_response(timeline.ambiance, self.sr)
        tail = len(ir) if mode == "full" and timeline.ambiance != "seco" else 0
        total = self._ms(timeline.total_duration_ms) + tail + self.sr // 2
        bed = np.zeros((2, total), dtype=np.float32)

        for p in timeline.placements:
            mono = clips.get(p.event_id)
            if mono is None or len(mono) == 0:
                continue
            stereo = self._place(p, np.asarray(mono, dtype=np.float32), mode)
            self._overlay(bed, stereo, self._ms(p.start_ms))

        if mode == "full" and timeline.ambiance != "seco":
            bed = dsp.convolution_reverb(bed, ir, wet=self.reverb_wet)

        return self._master(bed, mode)

    # ------------------------------------------------------------------ #
    def _place(self, p: Placement, mono: np.ndarray, mode: str) -> np.ndarray:
        n = len(mono)

        # ---- fala INTERROMPIDA: recorta e "afunda" com crossfade equal-power ----
        if p.hard_cut_ms is not None:
            cut = self._ms(p.hard_cut_ms - p.start_ms)
            if mode != "naive" and p.cut_snap_window_ms > 0:
                floor = min(self._ms(self.policy.min_audible_ms), n)
                cut = dsp.snap_to_valley(
                    mono, target=cut, window=self._ms(p.cut_snap_window_ms),
                    floor=floor, smooth_win=self._ms(5),
                )
            cut = max(1, min(cut, n))

            if mode == "naive":
                # cru: corte seco no ponto exato => clique digital
                seg = mono[:cut]
                return np.stack([seg, seg]).astype(np.float32)

            # estende ALÉM do corte pela janela de crossfade e desce em equal-power:
            # a voz anterior afunda (cos) exatamente sobre a subida (sin) da nova.
            xf = self._ms(p.crossfade_ms)
            end = min(n, cut + xf)
            seg = mono[:end]
            fade_out = max(end - cut, self._ms(p.fade_out_ms))
            seg = dsp.apply_fades(seg, self._ms(p.fade_in_ms), fade_out,
                                  curve_in="cosine", curve_out="equal_power")
            return dsp.equal_power_pan(seg, p.pan)

        if mode == "naive":
            return np.stack([mono, mono]).astype(np.float32)

        # ---- fala normal: fade-in equal-power se ela ENTRA sobre outra ----
        curve_in = "equal_power" if p.entry_type in ("interrupcao", "sobreposicao") else "cosine"
        mono = dsp.apply_fades(mono, self._ms(p.fade_in_ms), self._ms(p.fade_out_ms),
                               curve_in=curve_in)
        return dsp.equal_power_pan(mono, p.pan)

    @staticmethod
    def _overlay(bed: np.ndarray, stereo: np.ndarray, start: int) -> None:
        start = max(0, start)
        end = min(bed.shape[1], start + stereo.shape[1])
        if end > start:
            bed[:, start:end] += stereo[:, : end - start]

    def _master(self, bed: np.ndarray, mode: str) -> np.ndarray:
        if mode != "naive" and _HAS_PEDALBOARD:
            board = Pedalboard([HighpassFilter(cutoff_frequency_hz=65.0),
                                Limiter(threshold_db=-1.0)])
            processed = board(bed, self.sr)
            return dsp.peak_normalize(np.asarray(processed, dtype=np.float32), 0.94)
        return dsp.peak_normalize(bed, 0.89)

    # ------------------------------------------------------------------ #
    def write_wav(self, path: str, stereo: np.ndarray) -> None:
        stereo = np.asarray(stereo, dtype=np.float32)
        if _HAS_PEDALBOARD:
            with AudioFile(path, "w", self.sr, num_channels=stereo.shape[0]) as f:
                f.write(stereo)
        else:  # pragma: no cover — fallback stdlib
            import wave
            import struct
            data = (np.clip(stereo, -1, 1).T.reshape(-1) * 32767).astype("<i2")
            with wave.open(path, "w") as w:
                w.setnchannels(stereo.shape[0])
                w.setsampwidth(2)
                w.setframerate(self.sr)
                w.writeframes(struct.pack("<%dh" % len(data), *data))
