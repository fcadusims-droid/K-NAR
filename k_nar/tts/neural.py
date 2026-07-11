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

from k_nar.models import SpeechEvent
from k_nar.tts.base import RenderedClip


class PiperTTSBackend:
    def __init__(self, model_path: str, base_length_scale: float = 1.0):
        from piper import PiperVoice  # import tardio
        self.model_path = model_path
        self.voice = PiperVoice.load(model_path)
        self.sr = self.voice.config.sample_rate
        self.base_length_scale = base_length_scale

    @property
    def backend_id(self) -> str:
        # entra na chave de cache: muda de voz => invalida o cache
        import os
        return f"piper:{os.path.basename(self.model_path)}:ls{self.base_length_scale}"

    # ------------------------------------------------------------------ #
    def synthesize(self, event: SpeechEvent) -> RenderedClip:
        from piper.config import SynthesisConfig

        rate = event.voice.rate if event.voice.rate > 0 else 1.0
        tension = self._tension(event.voice.tension)

        # RELATIVO -> prosódia do Piper:
        #  length_scale menor = fala mais rápida; tensão acelera um pouco.
        #  noise_w_scale maior = entonação mais expressiva/variável.
        length_scale = self.base_length_scale / rate * (1.0 - 0.10 * tension)
        noise_w = 0.8 + 0.5 * tension
        cfg = SynthesisConfig(
            length_scale=float(max(0.4, length_scale)),
            noise_scale=1.0,
            noise_w_scale=float(noise_w),
            normalize_audio=True,
        )

        chunks = list(self.voice.synthesize(event.text, syn_config=cfg))
        if not chunks:
            return RenderedClip(event.id, 0, sample_rate=self.sr,
                                samples=np.zeros(1, np.float32))
        audio = np.concatenate([c.audio_float_array.astype(np.float32) for c in chunks])
        peak = float(np.max(np.abs(audio))) or 1.0
        audio = (audio / peak * 0.9).astype(np.float32)

        return RenderedClip(
            event_id=event.id,
            duration_ms=int(round(1000 * len(audio) / self.sr)),
            sample_rate=self.sr,
            samples=audio,
        )

    @staticmethod
    def _tension(value) -> float:
        labels = {"baixa": 0.15, "media": 0.5, "alta": 0.8, "extrema": 1.0}
        if isinstance(value, (int, float)):
            return float(min(max(value, 0.0), 1.0))
        return labels.get(str(value).strip().lower(), 0.0)
