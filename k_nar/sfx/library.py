"""LibrarySfxBackend — SOM REAL de uma biblioteca de samples, por tag.

É o backend de produção da visão: em vez de gerar tudo com IA, o motor CITA áudio
real. Um manifesto mapeia tag → arquivo(s) de som; o backend carrega, converte para
mono na taxa da cena, e devolve o `RenderedClip` com a duração REAL medida.

    manifest = {"tiro": ["sfx/tiro_01.wav", "sfx/tiro_02.wav"],
                "floresta_noite": ["amb/floresta.wav"]}
    backend = LibrarySfxBackend(manifest, sr=22050, fallback=ProceduralSfxBackend())

Se um tag não está no manifesto (ou o arquivo falha), cai no `fallback` (procedural)
— nunca um silêncio mudo e nunca um crash: a cena sempre rende. Vários arquivos por
tag dão variação (escolhe por hash do id do evento, determinístico).

Carregar áudio usa `pedalboard.io.AudioFile` (lida com wav/flac/mp3/ogg) e cai no
`wave` da stdlib para WAV se o pedalboard faltar.
"""

from __future__ import annotations

import zlib
from pathlib import Path

import numpy as np


def _stable_hash(s: str) -> int:
    """Hash ESTÁVEL entre processos (hash() é salgado): escolha de sample reprodutível."""
    return zlib.crc32(s.encode("utf-8")) & 0xFFFFFFFF

from k_nar.tts.base import RenderedClip

try:
    from pedalboard.io import AudioFile
    _HAS_PEDALBOARD = True
except Exception:  # pragma: no cover
    _HAS_PEDALBOARD = False


class LibrarySfxBackend:
    """Resolve tag → arquivo real de som. Satisfaz `SfxBackend`."""

    def __init__(self, manifest: dict[str, list[str] | str], sr: int = 22050,
                 base_dir: str = "", fallback=None, ambience_tags=None,
                 sfx_max_s: float = 2.5):
        # normaliza: cada tag guarda uma lista de caminhos
        self.manifest: dict[str, list[str]] = {
            tag: ([paths] if isinstance(paths, str) else list(paths))
            for tag, paths in manifest.items()
        }
        self.sr = sr
        self.base_dir = Path(base_dir) if base_dir else None
        self.fallback = fallback
        # ambiência é textura (não trimar, o renderer faz loop); SFX pontual é trimado
        # e limitado a `sfx_max_s` (clipes do ESC-50 têm 5s, muito com silêncio/cauda).
        if ambience_tags is None:
            from k_nar.sfx.catalog import AMBIENCE_TAGS
            ambience_tags = AMBIENCE_TAGS
        self.ambience_tags = set(ambience_tags)
        self.sfx_max_s = sfx_max_s

    @property
    def backend_id(self) -> str:
        return f"library_sfx:{self.sr}:{sorted(self.manifest)}"

    # ------------------------------------------------------------------ #
    def render(self, event) -> RenderedClip:
        tag = getattr(event, "tag", "") or ""
        paths = self.manifest.get(tag)
        if paths:
            # variação determinística por id do evento (mesmo id -> mesmo sample)
            choice = paths[_stable_hash(event.id) % len(paths)]
            path = self.base_dir / choice if self.base_dir else Path(choice)
            audio = self._load(path)
            if audio is not None and len(audio):
                audio = self._condition(audio, tag)
                return RenderedClip(
                    event_id=event.id,
                    duration_ms=int(round(1000 * len(audio) / self.sr)),
                    sample_rate=self.sr,
                    samples=audio,
                )
        # tag ausente ou falha de leitura: fallback auditável (nunca silêncio mudo)
        if self.fallback is not None:
            clip = self.fallback.render(event)
            return RenderedClip(event.id, clip.duration_ms, sample_rate=self.sr,
                                samples=clip.samples)
        return RenderedClip(event.id, 0, sample_rate=self.sr,
                            samples=np.zeros(1, np.float32))

    # ------------------------------------------------------------------ #
    def _condition(self, audio: np.ndarray, tag: str) -> np.ndarray:
        """Prepara o sample para o mix: ambiência fica como está (textura p/ loop);
        SFX pontual é trimado (tira o silêncio das bordas do clipe de 5s) e limitado.
        Normaliza o pico p/ o nível ficar previsível (ESC-50 varia muito de volume)."""
        from k_nar.render.dsp import peak_normalize, trim_silence
        if tag not in self.ambience_tags:
            trimmed, _, _ = trim_silence(audio, threshold_db=-35.0, keep_ms=20.0, sr=self.sr)
            if len(trimmed):
                audio = trimmed
            cap = int(self.sfx_max_s * self.sr)
            if len(audio) > cap:
                audio = audio[:cap]
        # peak_normalize opera em (canais, N); passamos mono como (1, N) e achatamos
        return peak_normalize(audio[None, :], target=0.9)[0]

    def _load(self, path: Path) -> np.ndarray | None:
        """Carrega áudio como mono float32 na taxa da cena. None se falhar."""
        if not path.exists():
            return None
        try:
            if _HAS_PEDALBOARD:
                with AudioFile(str(path)).resampled_to(self.sr) as f:
                    data = f.read(f.frames)
                mono = np.asarray(data, dtype=np.float32)
                mono = mono.mean(axis=0) if mono.ndim > 1 else mono
                return mono.astype(np.float32)
            return self._load_wav_stdlib(path)
        except Exception:  # pragma: no cover — arquivo corrompido/formato não suportado
            return None

    def _load_wav_stdlib(self, path: Path) -> np.ndarray | None:  # pragma: no cover
        import wave
        with wave.open(str(path), "rb") as w:
            n, ch, sw = w.getnframes(), w.getnchannels(), w.getsampwidth()
            raw = w.readframes(n)
            src_sr = w.getframerate()
        if sw != 2:
            return None  # só PCM16 no fallback stdlib
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        if ch > 1:
            data = data.reshape(-1, ch).mean(axis=1)
        if src_sr != self.sr:  # reamostragem linear simples
            from k_nar.render.dsp import resample_linear
            data = resample_linear(data, self.sr / src_sr)
        return data.astype(np.float32)
