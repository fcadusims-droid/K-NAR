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
        cut = f"  [CORTADA: {p.cut_method}]" if p.hard_cut_ms is not None else ""
        print(f"  {_fmt(p.start_ms)} {_fmt(p.end_ms)} pan={p.pan:>4} gain={p.gain_db:>5.1f}dB "
              f"{p.character:<8}{cut}")

    _diagnostico_alinhamento(scene, timeline, clips, sr, policy)

    out = Path("build_audio"); out.mkdir(exist_ok=True)
    renderer = TimelineRenderer(sr=sr, policy=policy)
    stereo = renderer.render(timeline, samples, mode="full")
    path = out / "neural_full.wav"
    renderer.write_wav(str(path), stereo)
    print(f"\naudio: {path.resolve()}  ({stereo.shape[1]/sr:.2f}s, {sr} Hz)")


def _diagnostico_alinhamento(scene, timeline, clips, sr, policy) -> None:
    """A/B do corte de interrupção: alvo matemático cru vs snap de energia vs
    FORCED ALIGNMENT (fronteira de fonema real do Piper).

    O degrau que o teste com áudio real apontou: o alvo proporcional cai no meio de
    um fonema (energia alta), e o snap de energia resgata a maioria mas às vezes erra
    (um vale que não é fronteira). O forced alignment do próprio VITS ancora o corte
    numa fronteira de palavra/fonema REAL — mostramos os três lado a lado.
    """
    print("\n--- DIAGNÓSTICO forced alignment (alvo cru | snap energia | fronteira fonema) ---")
    placements = {p.event_id: p for p in timeline.placements}
    events = list(scene.events)
    any_cut = False
    for i, ev in enumerate(events):
        p = placements.get(ev.id)
        if p is None or p.hard_cut_ms is None:
            continue
        any_cut = True
        clip = clips[ev.id]
        mono = np.asarray(clip.samples, dtype=np.float32)
        n = len(mono)
        align = clip.alignment
        smooth = int(0.005 * sr)
        energy = short_time_energy(mono, win=smooth)
        emed = float(np.mean(energy)) + 1e-9

        # alvo proporcional CRU (antes de qualquer snap), reconstruído da política
        nxt = events[i + 1] if i + 1 < len(events) else None
        agg = nxt.entry.aggressiveness if nxt else 0.0
        target = min(policy.interruption_start_within_prev(p.duration_ms, agg), n - 1)
        target_s = int(target / 1000 * sr)
        floor_s = min(int(policy.min_audible_ms / 1000 * sr), n)
        win_s = int(policy.cut_snap_window_ms / 1000 * sr)

        def ratio(s):
            return float(energy[min(max(s, 0), len(energy) - 1)]) / emed

        def verdict(r):
            return "vale limpo" if r < 0.4 else "aceitavel" if r < 1.0 else "ALTO(meio-fonema)"

        # 1) energia PURA na janela larga (o método antigo: pode vagar p/ meio de palavra)
        e_snap = snap_to_valley(mono, target=target_s, window=win_s, floor=floor_s, smooth_win=smooth)
        # 2) fronteira LINGUÍSTICA que o Orquestrador ancorou (hard_cut, pré-refino)
        edl_s = int((p.hard_cut_ms - p.start_ms) / 1000 * sr)
        # 3) refino do renderer: micro-vale numa janela ESTREITA ao redor da fronteira
        refine_s = snap_to_valley(mono, target=edl_s,
                                  window=int(p.cut_snap_window_ms / 1000 * sr),
                                  floor=floor_s, smooth_win=smooth)

        print(f"  {ev.id}  ({p.cut_method}):")
        print(f"      cru          {target_s/sr:5.2f}s  E/med={ratio(target_s):5.2f}  [{verdict(ratio(target_s))}]")
        print(f"      energia larga{e_snap/sr:5.2f}s  E/med={ratio(e_snap):5.2f}  [{verdict(ratio(e_snap))}]  (podia vagar p/ meio de palavra)")
        print(f"      fronteira    {edl_s/sr:5.2f}s  E/med={ratio(edl_s):5.2f}  [{verdict(ratio(edl_s))}]  (junto de {align.phoneme_at(edl_s)!r})" if align else "")
        print(f"      -> FINAL     {refine_s/sr:5.2f}s  E/med={ratio(refine_s):5.2f}  [{verdict(ratio(refine_s))}]  fronteira + refino acustico")
    if not any_cut:
        print("  (nenhuma interrupção nesta cena)")


if __name__ == "__main__":
    main()
