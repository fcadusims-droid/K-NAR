"""MultiVoiceTTSBackend — voz DISTINTA por personagem, atrás do mesmo `Protocol`.

O pitch por personagem (`ProsodyPolicy.character_pitch`) dá timbres diferentes a
partir de UM modelo mono-locutor — ajuda, mas não substitui vozes de verdade. Aqui
cada personagem aponta para um `VoiceProfile`: um modelo Piper próprio (voz real
diferente), um `speaker_id` (num modelo VITS multi-locutor) e ajustes finos de
pitch/ritmo. O roteamento por personagem é a única coisa nova; como satisfaz o
`TTSBackend`, o Orquestrador não muda uma linha.

Acoplamento: modelos são caros (~60MB, carrega uma vez). Este backend cacheia UM
`PiperTTSBackend` por (modelo, speaker_id) e roteia cada fala para o certo. O ajuste
de pitch por personagem entra pela `ProsodyPolicy` compartilhada (fonte única), e o
de ritmo por um multiplicador aplicado ao `rate` relativo da fala — nada de números
absolutos vazando para cá.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace

from k_nar.models import SpeechEvent
from k_nar.prosody import ProsodyPolicy
from k_nar.tts.base import RenderedClip


@dataclass
class VoiceProfile:
    """A "voz" de um personagem: qual modelo/locutor e os ajustes finos."""

    model_path: str | None = None    # modelo Piper próprio (None = usa o default)
    speaker_id: int | None = None    # locutor num modelo multi-speaker
    pitch_shift: float = 0.0         # semitons extra de timbre (via prosody)
    rate: float = 1.0                # multiplicador base de ritmo do personagem


class MultiVoiceTTSBackend:
    """Roteia cada fala para o backend Piper do personagem. Satisfaz `TTSBackend`."""

    def __init__(self, default_model: str,
                 profiles: dict[str, VoiceProfile] | None = None,
                 prosody: ProsodyPolicy | None = None,
                 align: bool = True):
        self.default_model = default_model
        self.profiles = profiles or {}
        self.align = align
        # Prosódia compartilhada (fonte única de pitch/rate/ganho). O pitch por
        # personagem do perfil é injetado aqui, para o TTS e o mix concordarem.
        self.prosody = copy.deepcopy(prosody or ProsodyPolicy())
        for character, prof in self.profiles.items():
            if prof.pitch_shift:
                self.prosody.character_pitch[character] = (
                    self.prosody.character_pitch.get(character, 0.0) + prof.pitch_shift)
        self._backends: dict[tuple[str, int | None], object] = {}

    # ------------------------------------------------------------------ #
    @property
    def backend_id(self) -> str:
        import os
        parts = [f"default={os.path.basename(self.default_model)}"]
        for ch in sorted(self.profiles):
            p = self.profiles[ch]
            model = os.path.basename(p.model_path) if p.model_path else "default"
            parts.append(f"{ch}={model}:spk{p.speaker_id}:p{p.pitch_shift}:r{p.rate}")
        return "multivoice(" + "|".join(parts) + ")"

    def _backend(self, model_path: str, speaker_id: int | None):
        """Backend Piper cacheado por (modelo, speaker_id). Carrega o modelo 1x."""
        key = (model_path, speaker_id)
        be = self._backends.get(key)
        if be is None:
            from k_nar.tts.neural import PiperTTSBackend  # import tardio (numpy/piper)
            be = PiperTTSBackend(model_path, prosody=self.prosody,
                                 align=self.align, speaker_id=speaker_id)
            self._backends[key] = be
        return be

    def synthesize(self, event: SpeechEvent) -> RenderedClip:
        prof = self.profiles.get(event.character, VoiceProfile())
        model = prof.model_path or self.default_model
        backend = self._backend(model, prof.speaker_id)
        # ritmo base do personagem: multiplica o rate RELATIVO da fala (nunca absoluto)
        if prof.rate != 1.0:
            base_rate = event.voice.rate if event.voice.rate > 0 else 1.0
            event = replace(event, voice=replace(event.voice, rate=base_rate * prof.rate))
        return backend.synthesize(event)
