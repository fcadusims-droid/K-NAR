"""K-NAR — um NARRADOR privado para conteúdo de redes sociais.

Você manda um roteiro (o texto de um vídeo/post) e o K-NAR devolve o áudio completo,
narrado por uma voz só, fiel ao texto — sem inventar som, trilha ou "atuação". A voz
sai de um motor neural local (XTTS-v2), então nada do seu roteiro precisa sair da sua
máquina.

    from k_nar import load_script, narrate_script
    script = load_script("roteiro.txt")
    res = narrate_script(script, engine="xtts")   # ou "formante" (rascunho offline)
    res.write_wav("narracao.wav")

O núcleo (segmentação do roteiro, leitura do front-matter) é stdlib puro; numpy só é
exigida na montagem do áudio, e o motor XTTS (torch/coqui) é carregado sob demanda.
"""

from k_nar.models import SpeechEvent, VoiceParams
from k_nar.narrator import (
    NarrationConfig,
    NarrationResult,
    Segment,
    build_backend,
    narrate,
    narrate_script,
    segment_script,
)
from k_nar.script import Script, load_script, parse_script
from k_nar.tts.base import RenderedClip, TTSBackend

__all__ = [
    "NarrationConfig",
    "NarrationResult",
    "RenderedClip",
    "Script",
    "Segment",
    "SpeechEvent",
    "TTSBackend",
    "VoiceParams",
    "build_backend",
    "load_script",
    "narrate",
    "narrate_script",
    "parse_script",
    "segment_script",
]

__version__ = "0.2.0"
