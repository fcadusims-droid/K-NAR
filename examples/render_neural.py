"""Pipeline NEURAL completo: roteiro -> Director -> [Piper + cache + paralelo] -> audio.

Expõe o Orquestrador e o nó de DSP à voz neural real (Piper): fonemas, plosivas,
respiração e prosódia intrínseca. É o teste de fogo do pipeline de duas passagens
sob condições reais de áudio.

    python -m examples.render_neural [roteiro.json]

Demonstra as respostas à latência do TTS:
  * cache em disco (.knar_cache): 2a execução não re-sintetiza nada;
  * síntese paralela (synthesize_all): passagem 2 roda em pool, não em série.

Também DIAGNOSTICA o snap_to_valley sobre o áudio real (onde o corte caiu e qual
a energia ali) — para ver se o vale encontrado é silêncio legítimo ou meio-fonema.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

from k_nar import Orquestrador, ProsodyPolicy, Scene, TimingPolicy
from k_nar.director import RuleBasedDirector
from k_nar.render.dsp import short_time_energy, snap_to_valley
from k_nar.render.renderer import TimelineRenderer
from k_nar.render.trim import TrimmedTTS
from k_nar.tts.batch import synthesize_all
from k_nar.tts.cache import CachingTTS
from k_nar.tts.neural import PiperTTSBackend

VOICE = "models/piper/pt_BR-faber-medium.onnx"
MODEL = "models/qwen2.5-1.5b-instruct-q4_k_m.gguf"


def _fmt(ms: int) -> str:
    return f"{ms / 1000:6.2f}s"


def _director(use_llm: bool):
    if use_llm and Path(MODEL).exists():
        from k_nar.director.llama import LlamaDirector
        print(f"[director] LLM local (few-shot): {Path(MODEL).name}")
        return LlamaDirector(MODEL, n_threads=4)
    print("[director] RuleBasedDirector")
    return RuleBasedDirector()


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--llm"]
    use_llm = "--llm" in sys.argv
    roteiro = Path(args[0]) if args else Path(__file__).parent / "roteiro_exemplo.json"
    if not Path(VOICE).exists():
        print(f"voz Piper ausente: {VOICE}\nrode: scripts/download_piper.sh")
        return

    scene = Scene.from_dict(_director(use_llm).direct(json.loads(roteiro.read_text("utf-8"))))

    # UMA matriz de prosódia compartilhada entre TTS (pitch/rate/variância) e
    # Orquestrador (ganho de dinâmica) -> síntese e mix concordam, nada "descolado".
    prosody = ProsodyPolicy()
    piper = PiperTTSBackend(VOICE, prosody=prosody)
    backend = CachingTTS(TrimmedTTS(piper), cache_dir=".knar_cache")
    sr = piper.sr
    policy = TimingPolicy()

    # PASSAGEM 2 em paralelo (com cache)
    t = time.time()
    clips = synthesize_all(backend, scene.events, workers=4)
    print(f"[passagem 2] {len(clips)} falas sintetizadas em {time.time()-t:.2f}s "
          f"(cache: {backend.hits} hits, {backend.misses} misses)")

    # PASSAGENS 3+4
    timeline = Orquestrador(backend, policy, prosody=prosody).render_scene(scene, clips=clips)
    samples = {eid: c.samples for eid, c in clips.items()}

    print(f"\n--- TIMELINE ({_fmt(timeline.total_duration_ms)}) ---")
    for p in timeline.placements:
        cut = "  [CORTADA]" if p.hard_cut_ms is not None else ""
        print(f"  {_fmt(p.start_ms)} {_fmt(p.end_ms)} pan={p.pan:>4} gain={p.gain_db:>5.1f}dB "
              f"{p.character:<8}{cut}")

    _diagnostico_snap(timeline, samples, sr, policy)

    out = Path("build_audio"); out.mkdir(exist_ok=True)
    renderer = TimelineRenderer(sr=sr, policy=policy)
    stereo = renderer.render(timeline, samples, mode="full")
    path = out / "neural_full.wav"
    renderer.write_wav(str(path), stereo)
    print(f"\naudio: {path.resolve()}  ({stereo.shape[1]/sr:.2f}s, {sr} Hz)")


def _diagnostico_snap(timeline, samples, sr, policy) -> None:
    """Compara o corte no ALVO puramente matemático vs. onde o snap de fato corta.

    No áudio neural real, o alvo proporcional cru costuma cair no meio de um fonema
    (energia alta) — o que arruinaria a inteligibilidade. O snap desliza para o vale
    de energia (silêncio entre palavras). Este diagnóstico mostra os dois lados, e é
    a prova de que o snap faz trabalho REAL sobre a voz humana (o mock escondia isso).
    """
    print("\n--- DIAGNÓSTICO snap_to_valley (áudio real: alvo cru vs snapped) ---")
    any_cut = False
    for p in timeline.placements:
        if p.hard_cut_ms is None:
            continue
        any_cut = True
        mono = np.asarray(samples[p.event_id], dtype=np.float32)
        n = len(mono)
        target = min(int((p.hard_cut_ms - p.start_ms) / 1000 * sr), n - 1)
        floor = min(int(policy.min_audible_ms / 1000 * sr), n)
        snapped = snap_to_valley(mono, target=target, window=int(p.cut_snap_window_ms / 1000 * sr),
                                 floor=floor, smooth_win=int(0.005 * sr))
        energy = short_time_energy(mono, win=int(0.005 * sr))
        emed = float(np.mean(energy)) + 1e-9
        r_target = float(energy[target]) / emed
        r_snap = float(energy[min(snapped, len(energy) - 1)]) / emed
        verdict = "vale limpo" if r_snap < 0.4 else "aceitavel" if r_snap < 1.0 else "ainda alto"
        print(f"  {p.event_id}: alvo {target/sr:.2f}s (E/med={r_target:.2f}, meio-fonema) "
              f"-> snap {snapped/sr:.2f}s (E/med={r_snap:.2f}, {verdict})  desloc {abs(snapped-target)/sr*1000:.0f}ms")
    if not any_cut:
        print("  (nenhuma interrupção nesta cena)")


if __name__ == "__main__":
    main()
