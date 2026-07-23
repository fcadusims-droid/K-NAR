"""XTTSBackend — voz neural de ALTA qualidade (Coqui XTTS-v2), atrás do mesmo Protocol.

Piper "medium" é o teto de timbre hoje (não há voz "high" em pt). O XTTS-v2 é um salto
de naturalidade — multilíngue, com prosódia bem mais viva — e satisfaz o mesmo
`TTSBackend`, então o Orquestrador não muda uma linha. Reaproveita a `ProsodyPolicy` +
`EmotionPolicy`: a EMOÇÃO vira `speed` (ritmo) no XTTS e o pitch é aplicado por
reamostragem (como no Piper), mantendo a atuação coerente entre os dois motores.

Custo honesto: XTTS em CPU é LENTO (segundos por frase) e o modelo pesa ~1.8GB (baixado
na 1ª vez). Por isso é OPT-IN (o pipeline usa Piper por padrão; `--voz xtts` liga isto).
Os imports pesados (torch/TTS) são TARDIOS — o core segue stdlib-puro.
"""

from __future__ import annotations

from k_nar.models import SpeechEvent
from k_nar.prosody import ProsodyPolicy
from k_nar.tts.base import RenderedClip

# cache de modelos por nome (carregar XTTS custa caro: uma vez por processo).
_MODELS: dict[str, object] = {}

# locutores de estúdio do XTTS-v2 por gênero — a diferenciação de voz por personagem
# vem DAQUI (não do pitch): cada personagem ganha um locutor distinto.
_FEMALE_SPK = ("Daisy Studious", "Gracie Wise", "Ana Florence", "Sofia Hellen",
               "Alison Dietlinde", "Tammie Ema", "Brenda Stern", "Henriette Usha")
_MALE_SPK = ("Dionisio Schuyler", "Royston Min", "Viktor Eka", "Abrahan Mack",
             "Baldur Sanjin", "Craig Gutsy", "Andrew Chipper", "Badr Odhiambo")


def assign_speakers(traits: dict, narrator: str = "Narrador") -> dict[str, str]:
    """Mapeia personagem → locutor de estúdio XTTS pelo gênero inferido (casting),
    round-robin p/ vozes distintas. `traits`: dict[personagem -> casting.Traits]."""
    out: dict[str, str] = {}
    fi = mi = 0
    for ch in sorted(traits):
        t = traits[ch]
        if getattr(t, "gender", "?") == "f":
            out[ch] = _FEMALE_SPK[fi % len(_FEMALE_SPK)]; fi += 1
        else:
            out[ch] = _MALE_SPK[mi % len(_MALE_SPK)]; mi += 1
    out.setdefault(narrator, _MALE_SPK[mi % len(_MALE_SPK)])
    return out


class XTTSBackend:
    """Satisfaz `TTSBackend`. Roteia cada fala pelo XTTS-v2, com voz por personagem
    (locutor de estúdio ou áudio de referência) + prosódia/emoção compartilhadas."""

    MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
    # mapa idioma K-NAR → código XTTS
    _LANG = {"pt": "pt", "en": "en", "es": "es"}

    def __init__(self, language: str = "pt", speaker: str | None = None,
                 speakers: dict[str, str] | None = None,
                 speaker_wavs: dict[str, str] | None = None,
                 prosody: ProsodyPolicy | None = None, align: bool = False):
        self.language = self._LANG.get(str(language)[:2], "pt")
        self.speaker = speaker
        self.speakers = speakers or {}          # personagem -> locutor de estúdio
        self.speaker_wavs = speaker_wavs or {}  # personagem -> wav de referência (clonagem)
        self.prosody = prosody or ProsodyPolicy()
        self.align = False                      # XTTS não exporta forced alignment
        self._tts = None
        self._sr = 24000

    # ------------------------------------------------------------------ #
    @property
    def backend_id(self) -> str:
        return f"xtts({self.language}|spk={self.speaker or 'auto'})"

    def _load(self):
        if self._tts is not None:
            return self._tts
        tts = _MODELS.get(self.MODEL)
        if tts is None:
            from TTS.api import TTS  # import TARDIO (torch/coqui)
            tts = TTS(self.MODEL, progress_bar=False)
            _MODELS[self.MODEL] = tts
        self._tts = tts
        try:
            self._sr = int(tts.synthesizer.output_sample_rate)
        except Exception:  # pragma: no cover
            self._sr = 24000
        return tts

    def _default_speaker(self, tts) -> str | None:
        if self.speaker:
            return self.speaker
        # primeiro locutor de estúdio disponível (XTTS multi-speaker)
        names = getattr(getattr(tts, "synthesizer", None), "tts_model", None)
        try:
            spk = list(tts.speakers) if getattr(tts, "speakers", None) else None
            return spk[0] if spk else None
        except Exception:  # pragma: no cover
            return None

    def synthesize(self, event: SpeechEvent) -> RenderedClip:
        import numpy as np

        tts = self._load()
        text = (event.text or "").strip()
        if not text:
            return RenderedClip(event.id, 0, sample_rate=self._sr, samples=np.zeros(0, np.float32))

        # prosódia/emoção compartilhadas: emoção → speed (ritmo); pitch por reamostragem.
        # character="" de propósito: no XTTS a voz por personagem vem do LOCUTOR, não do
        # pitch — o pitch fica só a serviço da EMOÇÃO.
        pros = self.prosody.resolve(
            ProsodyPolicy.tension_scalar(event.voice.tension),
            rate=event.voice.rate if event.voice.rate > 0 else 1.0,
            character="",
            emotion=getattr(event.voice, "emotion", "neutro"),
            intensity=getattr(event.voice, "intensity", 0.0))
        # length_scale >1 = mais lento → speed = 1/length_scale (limitado p/ não distorcer)
        speed = float(max(0.6, min(1.6, 1.0 / max(pros.length_scale, 0.1))))

        kwargs = dict(text=text, language=self.language, speed=speed)
        wav_ref = self.speaker_wavs.get(event.character)
        if wav_ref:
            kwargs["speaker_wav"] = wav_ref
        else:
            spk = self.speakers.get(event.character) or self._default_speaker(tts)
            if spk:
                kwargs["speaker"] = spk

        wav = np.asarray(tts.tts(**kwargs), dtype=np.float32)

        # pitch por reamostragem (mesmo truque do Piper): sobe/desce o tom sem SSML.
        p = 2.0 ** (pros.pitch_semitones / 12.0)
        if abs(pros.pitch_semitones) > 0.05 and len(wav):
            from k_nar.render import dsp
            slow = dsp.resample_linear(wav, p)         # estica/comprime
            wav = dsp.resample_linear(slow, 1.0 / p * (len(wav) / max(len(slow), 1)))
            wav = wav[: len(slow)] if len(wav) > len(slow) else wav

        dur_ms = int(round(1000 * len(wav) / self._sr))
        return RenderedClip(event.id, dur_ms, sample_rate=self._sr, samples=wav)
