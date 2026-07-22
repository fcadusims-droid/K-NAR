"""PiperTTSBackend — TTS NEURAL real (Piper/onnx), rodando em CPU.

Substitui o mock/formante por voz com fonemas de verdade: plosivas, fricativas,
respiração e prosódia intrínseca. É exatamente essa "assinatura de energia" real
que estressa o `snap_to_valley` e o mapeamento de tempo do pipeline de duas
passagens — o ponto cego que o mock mascarava.

Implementa o Protocol `TTSBackend`: devolve `RenderedClip` com `samples` (mono
float32) e `duration_ms` MEDIDO do áudio sintetizado. Traduz os parâmetros
RELATIVOS de voz (rate, tensão) para os controles de prosódia do Piper — o LLM
nunca fala em segundos; o mapeamento vive aqui.

Nota de acoplamento: este arquivo importa numpy/piper, mas NÃO é importado pelo
core (`k_nar/__init__`). Trocar Piper por XTTS = outro backend, mesmo contrato.
"""

from __future__ import annotations

import numpy as np

from k_nar.align import Alignment
from k_nar.models import SpeechEvent
from k_nar.prosody import ProsodyPolicy
from k_nar.render.dsp import resample_linear
from k_nar.tts.base import RenderedClip


class PiperTTSBackend:
    def __init__(self, model_path: str, prosody: ProsodyPolicy | None = None,
                 align: bool = True, speaker_id: int | None = None):
        from piper import PiperVoice  # import tardio
        self.model_path = model_path
        # Locutor num modelo Piper multi-speaker (VITS pode ter vários). None = mono.
        self.speaker_id = speaker_id
        # include_alignments=True faz o Piper expor a duração por fonema (forced
        # alignment do próprio VITS). Requer o pacote `onnx` para o patch em memória;
        # sem ele, seguimos sem alinhamento e o corte cai no snap de energia.
        self.align = align
        try:
            self.voice = PiperVoice.load(model_path, include_alignments=align)
            self._has_align = align
        except Exception:  # pragma: no cover — onnx ausente / modelo não-patchável
            self.voice = PiperVoice.load(model_path)
            self._has_align = False
        self.sr = self.voice.config.sample_rate
        self.prosody = prosody or ProsodyPolicy()

    @property
    def backend_id(self) -> str:
        # entra na chave de cache: muda de voz/prosódia => invalida o cache
        import os
        p = self.prosody
        sig = f"{p.length_scale_calm},{p.length_scale_tense},{p.pitch_calm},{p.pitch_tense}"
        spk = "" if self.speaker_id is None else f":spk{self.speaker_id}"
        return f"piper:{os.path.basename(self.model_path)}{spk}:{sig}"

    # ------------------------------------------------------------------ #
    def synthesize(self, event: SpeechEvent) -> RenderedClip:
        from piper.config import SynthesisConfig

        rate = event.voice.rate if event.voice.rate > 0 else 1.0
        tension = ProsodyPolicy.tension_scalar(event.voice.tension)
        pros = self.prosody.resolve(tension, rate=rate, character=event.character)

        # pitch por reamostragem: gera mais LENTO por fator p e reamostra de volta,
        # subindo o pitch em p sem alterar a duração-alvo (length_scale).
        p = 2.0 ** (pros.pitch_semitones / 12.0)
        length_scale_synth = float(max(0.4, pros.length_scale * p))

        cfg = SynthesisConfig(
            length_scale=length_scale_synth,
            noise_scale=float(pros.noise_scale),
            noise_w_scale=float(pros.noise_w),
            normalize_audio=True,
            speaker_id=self.speaker_id,
        )
        chunks = list(self.voice.synthesize(
            event.text, syn_config=cfg, include_alignments=self._has_align))
        if not chunks:
            return RenderedClip(event.id, 0, sample_rate=self.sr,
                                samples=np.zeros(1, np.float32))
        audio = np.concatenate([c.audio_float_array.astype(np.float32) for c in chunks])

        # Forced alignment: concatena os fonemas de todos os chunks no domínio de
        # amostras CRU (pré-reamostragem), acompanhando os offsets de áudio.
        alignment = self._collect_alignment(chunks)

        # reamostra por 1/p -> pitch x p, duração volta ao alvo de length_scale
        if abs(p - 1.0) > 1e-3:
            audio = resample_linear(audio, 1.0 / p)
            if alignment is not None:
                alignment = alignment.scaled(1.0 / p)

        peak = float(np.max(np.abs(audio))) or 1.0
        audio = (audio / peak * 0.9).astype(np.float32)

        return RenderedClip(
            event_id=event.id,
            duration_ms=int(round(1000 * len(audio) / self.sr)),
            sample_rate=self.sr,
            samples=audio,
            alignment=alignment,
        )

    # ------------------------------------------------------------------ #
    def _collect_alignment(self, chunks) -> Alignment | None:
        """Junta `phoneme_alignments` de todos os chunks num só `Alignment`.

        Cada chunk alinha só o próprio áudio; ao concatenar o áudio, os offsets de
        fonema precisam acumular o comprimento dos chunks anteriores.
        """
        if not self._has_align:
            return None
        merged = []
        for c in chunks:
            al = getattr(c, "phoneme_alignments", None)
            if not al:
                return None  # um chunk sem alinhamento invalida o corte fonético
            merged.extend(al)
        if not merged:
            return None
        return Alignment.from_piper(merged, self.sr)
