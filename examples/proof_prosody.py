"""Prova do Mapeamento de Expressividade: a MESMA frase em 4 tensões.

O Piper é emocionalmente inerte — não muda a entonação pela semântica. Toda a
expressividade vem da ProsodyPolicy, que abre a tensão em rate (velocidade),
pitch (agudo/grave) e ganho (dinâmica). Aqui sintetizamos a mesma frase em
baixa/media/alta/extrema e mostramos que os três eixos de fato se movem — e
gravamos as 4 versões em sequência para ouvir o contraste.

    python -m examples.proof_prosody   ->   build_audio/prosody_contraste.wav
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from k_nar.models import SpeechEvent, VoiceParams
from k_nar.prosody import ProsodyPolicy
from k_nar.render.renderer import TimelineRenderer
from k_nar.tts.neural import PiperTTSBackend

VOICE = "models/piper/pt_BR-faber-medium.onnx"
TEXTO = "Nos nao temos mais tempo, precisamos decidir isso agora."


def _centroid(x: np.ndarray, sr: int) -> float:
    X = np.abs(np.fft.rfft(x))
    f = np.fft.rfftfreq(len(x), 1 / sr)
    return float((f * X).sum() / (X.sum() + 1e-9))


def main() -> None:
    if not Path(VOICE).exists():
        print(f"voz ausente: {VOICE}\nrode: scripts/download_piper.sh")
        return
    prosody = ProsodyPolicy()
    piper = PiperTTSBackend(VOICE, prosody=prosody)
    sr = piper.sr

    print(f"frase fixa: \"{TEXTO}\"\n")
    print(f"{'tensao':>8} {'dur_ms':>7} {'centroide_Hz':>13} {'gain_dB':>8}")
    segments = []
    for tens in ("baixa", "media", "alta", "extrema"):
        ev = SpeechEvent(id=tens, character="A", text=TEXTO, voice=VoiceParams(tension=tens))
        clip = piper.synthesize(ev)
        x = np.asarray(clip.samples, dtype=np.float32)
        g = prosody.resolve(ProsodyPolicy.tension_scalar(tens)).gain_db
        print(f"{tens:>8} {clip.duration_ms:>7} {_centroid(x, sr):>13.0f} {g:>8.1f}")
        # aplica o ganho de dinâmica e um respiro de 0.4s entre as versões
        x = x * (10.0 ** (g / 20.0))
        segments.append(x)
        segments.append(np.zeros(int(0.4 * sr), np.float32))

    mono = np.concatenate(segments)
    stereo = np.stack([mono, mono]).astype(np.float32)
    out = Path("build_audio"); out.mkdir(exist_ok=True)
    r = TimelineRenderer(sr=sr)
    path = out / "prosody_contraste.wav"
    r.write_wav(str(path), r._master(stereo, "full"))
    print(f"\naudio (4 tensões em sequência): {path.resolve()}")


if __name__ == "__main__":
    main()
