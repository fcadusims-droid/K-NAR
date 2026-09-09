"""O NARRADOR — o produto do K-NAR: roteiro → um arquivo de áudio narrado.

Você manda um roteiro (o texto de um vídeo, um post, um script de redes), e o K-NAR
devolve o áudio completo, narrado por uma voz só, na ordem do roteiro, sem inventar
nada — sem SFX, sem trilha, sem "atuação" que você não pediu. É o oposto do modo
história antigo (que INFERIA drama da prosa): aqui a regra é FIDELIDADE ao roteiro.

Três passos:

    1. SEGMENTAR   — o texto vira frases (respiro curto entre elas) agrupadas em
                     parágrafos (respiro maior entre eles). É só onde as pausas caem.
    2. SINTETIZAR  — cada frase passa pelo motor de voz (XTTS por padrão), com trim de
                     silêncio + cache (reeditar uma frase não re-sintetiza o resto).
    3. MONTAR      — concatena tudo com as pausas, normaliza e escreve um WAV (ou, via
                     `package_audio`, um .ogg/.mp3 sob um limite de tamanho).

O motor de voz é agnóstico (o mesmo `TTSBackend` do resto): XTTS-v2 local (voz de
alta qualidade, privada), ou o `FormantTTSBackend` (stand-in offline, p/ rascunho e
testes sem baixar torch). A `numpy` só é exigida na montagem (passo 3).
"""

from __future__ import annotations

import re
import wave
from dataclasses import dataclass, field
from pathlib import Path

from k_nar.models import SpeechEvent, VoiceParams
from k_nar.tts.base import RenderedClip, TTSBackend

# Locutor de estúdio padrão do narrador (XTTS): voz MASCULINA, grave e calma — um
# "narrador" de verdade, em vez do 1º locutor alfabético (que é feminino). Sobrescrevível
# por --locutor / front-matter `locutor:`.
XTTS_DEFAULT_SPEAKER = "Damien Black"

# Pontuação terminal a remover do fim de cada bloco antes de sintetizar: o XTTS tende a
# VOCALIZAR/artefatar a pontuação no fim de um trecho ("ponto", clique). Os pontos
# INTERNOS ficam — dentro de um parágrafo o XTTS os trata como pausa natural, não palavra.
_TERMINAL_PUNCT = re.compile(r"[\s.;:,…!?]+$")


@dataclass
class NarrationConfig:
    """As alavancas de ritmo/nível da narração — o "estilo de leitura" num objeto só."""

    speed: float = 1.0             # 1.0 neutro; >1 acelera, <1 desacelera
    paragraph_pause_ms: int = 700  # silêncio entre parágrafos (a pausa ENTRE frases é
                                   # do próprio motor, que lê o parágrafo com prosódia contínua)
    lead_ms: int = 150             # silêncio no começo do arquivo
    tail_ms: int = 400             # silêncio no fim
    peak_dbfs: float = -1.0        # normalização de pico do arquivo final


@dataclass
class Segment:
    """Um BLOCO a narrar (um parágrafo) + a pausa que o segue. Sintetizar o parágrafo
    inteiro (e não frase a frase) dá prosódia natural e evita o artefato de pontuação
    que o XTTS produz no fim de trechos curtos isolados."""

    id: str
    text: str
    pause_after_ms: int


@dataclass
class NarrationResult:
    audio: object          # np.ndarray mono float32 em [-1, 1]
    sr: int
    segments: list          # list[Segment]
    duration_ms: int
    voice_kind: str         # "xtts" | "formante" | ...
    cache_hits: int = 0
    cache_misses: int = 0

    def write_wav(self, path: str | Path) -> str:
        """Escreve o áudio como WAV mono PCM 16-bit (stdlib `wave`, sem dependências)."""
        import numpy as np

        mono = np.asarray(self.audio, dtype=np.float32)
        pcm = (np.clip(mono, -1.0, 1.0) * 32767.0).astype("<i2")
        path = str(path)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sr)
            w.writeframes(pcm.tobytes())
        return path

    def package(self, out_prefix: str, *, fmt: str = "opus", max_mb: float = 28.0,
                bitrate: int = 96) -> list[str]:
        """Entrega sob um limite de tamanho: .ogg (Opus) ou .mp3, dividido em partes
        (cortando no silêncio) se passar do teto. Requer as libs de `scripts/package_audio`."""
        import sys

        import numpy as np

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from package_audio import package  # noqa: E402

        stereo = np.asarray(self.audio, dtype=np.float32).reshape(-1, 1)
        return package(stereo, self.sr, out_prefix, max_mb=max_mb, fmt=fmt, bitrate=bitrate)


# ------------------------------------------------------------------------- #
#  Passo 1 — segmentação                                                    #
# ------------------------------------------------------------------------- #
def _strip_terminal(text: str) -> str:
    """Remove pontuação/espaço no FIM do bloco (o que o XTTS tende a vocalizar). Os sinais
    internos ficam — o motor lê o parágrafo com pausas naturais nos pontos internos."""
    return _TERMINAL_PUNCT.sub("", text.strip())


def segment_script(text: str, config: NarrationConfig | None = None) -> list[Segment]:
    """Quebra o roteiro em BLOCOS = parágrafos (separados por linha em branco). Cada
    bloco é sintetizado inteiro (prosódia contínua, sem o corte robótico frase a frase);
    entre blocos entra uma pausa. A pontuação terminal de cada bloco é removida.

    O texto já vem limpo de Markdown pelo leitor de roteiro.
    """
    config = config or NarrationConfig()
    paragraphs = [re.sub(r"\s+", " ", p).strip()
                  for p in re.split(r"\n\s*\n", text) if p.strip()]
    blocks = [_strip_terminal(p) for p in paragraphs]
    blocks = [b for b in blocks if b]
    segments: list[Segment] = []
    for i, block in enumerate(blocks):
        last = i == len(blocks) - 1
        segments.append(Segment(id=f"n{i:04d}", text=block,
                                pause_after_ms=0 if last else config.paragraph_pause_ms))
    return segments


# ------------------------------------------------------------------------- #
#  Passo 3 — montagem                                                       #
# ------------------------------------------------------------------------- #
def assemble(clips: list[RenderedClip], segments: list[Segment], sr: int,
             config: NarrationConfig) -> "object":
    """Concatena os clipes na ordem, inserindo as pausas de cada segmento + lead/tail,
    e normaliza o pico. Devolve um np.ndarray mono float32."""
    import numpy as np

    def _silence(ms: int):
        return np.zeros(max(0, int(round(ms / 1000.0 * sr))), dtype=np.float32)

    parts: list = [_silence(config.lead_ms)]
    by_id = {c.event_id: c for c in clips}
    for seg in segments:
        clip = by_id.get(seg.id)
        if clip is not None and clip.samples is not None and len(clip.samples):
            parts.append(np.asarray(clip.samples, dtype=np.float32))
        if seg.pause_after_ms:
            parts.append(_silence(seg.pause_after_ms))
    parts.append(_silence(config.tail_ms))

    audio = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak > 0:
        target = 10.0 ** (config.peak_dbfs / 20.0)
        audio = (audio * (target / peak)).astype(np.float32)
    return audio


# ------------------------------------------------------------------------- #
#  Orquestração dos três passos                                             #
# ------------------------------------------------------------------------- #
def _events(segments: list[Segment], speed: float) -> list[SpeechEvent]:
    """Cada frase vira um evento de fala NEUTRO (sem drama): tensão 0, emoção neutra,
    `rate = speed`. É o que garante a leitura fiel — nada de "voz de suspense"."""
    return [SpeechEvent(id=s.id, character="Narrador", text=s.text,
                        voice=VoiceParams(tension=0.0, rate=speed, emotion="neutro"))
            for s in segments]


def build_backend(engine: str = "xtts", *, lang: str = "pt", locutor: str = "",
                  voice_ref: str = "", cache_dir: str = ".knar_cache") -> TTSBackend:
    """Monta o motor de voz do narrador (imports pesados são TARDIOS).

    - `xtts` (padrão): voz neural de alta qualidade, local e privada. Locutor de
      estúdio (`locutor`) OU clonagem da sua voz (`voice_ref` = wav de referência).
      Envolto em trim de silêncio + cache. Uma PROSÓDIA NEUTRA (nada de drama): a
      leitura sai fiel ao texto, e `speed` (via `rate`) é o único controle de ritmo.
    - `formante`: stand-in sintético offline (sem torch), p/ rascunho e testes.
    """
    if engine == "formante":
        from k_nar.render.voice import FormantTTSBackend
        backend = FormantTTSBackend(sr=24000)
        backend.voice_kind = "formante"
        return backend

    if engine != "xtts":
        raise ValueError(f"motor de voz desconhecido: {engine!r} (use 'xtts' ou 'formante')")

    from k_nar.prosody import ProsodyPolicy
    from k_nar.render.trim import TrimmedTTS
    from k_nar.tts.cache import CachingTTS
    from k_nar.tts.xtts import XTTSBackend

    # Prosódia NEUTRA: âncoras calmo==tenso==1.0 e pitch 0 — o narrador não "atua".
    neutral = ProsodyPolicy(length_scale_calm=1.0, length_scale_tense=1.0,
                            pitch_calm=0.0, pitch_tense=0.0)
    speaker_wavs = {"Narrador": voice_ref} if voice_ref else None
    # sem locutor nem clonagem → voz masculina padrão do narrador (não a 1ª alfabética).
    speaker = locutor or (None if voice_ref else XTTS_DEFAULT_SPEAKER)
    xtts = XTTSBackend(language=lang, speaker=speaker,
                       speaker_wavs=speaker_wavs, prosody=neutral)
    backend = CachingTTS(TrimmedTTS(xtts), cache_dir=cache_dir)
    backend.voice_kind = "xtts"
    return backend


def narrate_script(script, *, engine: str = "xtts", cache_dir: str = ".knar_cache",
                   workers: int = 1) -> NarrationResult:
    """Atalho: um `Script` (do leitor de roteiro) → `NarrationResult`. Monta o motor de
    voz a partir das opções do roteiro e roda os três passos."""
    config = NarrationConfig(
        speed=script.speed,
        paragraph_pause_ms=script.paragraph_pause_ms,
    )
    backend = build_backend(engine, lang=script.lang, locutor=script.locutor,
                            voice_ref=script.voice_ref, cache_dir=cache_dir)
    return narrate(script.text, backend, config=config, workers=workers)


def narrate(text: str, backend: TTSBackend, *, config: NarrationConfig | None = None,
            workers: int = 1) -> NarrationResult:
    """Roda os três passos: segmenta o texto, sintetiza cada frase pelo `backend` e
    monta o áudio final. `backend` já vem configurado (voz/idioma) pelo chamador.

    `workers=1` por padrão: o XTTS (torch) não é thread-safe para inferência concorrente
    numa mesma instância, e o torch já paraleliza entre núcleos por dentro de cada chamada.
    """
    from k_nar.tts.batch import synthesize_all

    config = config or NarrationConfig()
    segments = segment_script(text, config)
    if not segments:
        raise ValueError("roteiro vazio: nenhuma frase para narrar")

    events = _events(segments, config.speed)
    clips_by_id = synthesize_all(backend, events, workers=workers)
    clips = [clips_by_id[e.id] for e in events if e.id in clips_by_id]

    sr = next((c.sample_rate for c in clips if c.sample_rate), 24000)
    audio = assemble(clips, segments, sr, config)
    dur_ms = int(round(1000 * len(audio) / sr)) if len(audio) else 0

    return NarrationResult(
        audio=audio, sr=sr, segments=segments, duration_ms=dur_ms,
        voice_kind=getattr(backend, "voice_kind", type(backend).__name__),
        cache_hits=getattr(backend, "hits", 0),
        cache_misses=getattr(backend, "misses", 0),
    )
