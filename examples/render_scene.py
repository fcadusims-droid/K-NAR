"""Render de ponta a ponta: JSON da cena -> Timeline -> áudio real (WAV).

Gera três versões da MESMA cena para um A/B acústico honesto:

    01_naive.wav  -> corte cru no hard_cut_ms (clique), sem pan, sem reverb
    02_dry.wav    -> fades anti-clique + snap ao vale + palco estéreo (sem espaço)
    03_full.wav   -> tudo acima + bus de reverb convolutivo (coesão acústica)

Uso:
    python -m examples.render_scene [cena.json] [dir_saida]

Roda offline. Requer numpy (e pedalboard p/ o master; sem ele, cai no fallback).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from k_nar import Orquestrador, Scene, TimingPolicy
from k_nar.render.renderer import TimelineRenderer
from k_nar.render.trim import TrimmedTTS
from k_nar.render.voice import FormantTTSBackend

SR = 24000


def _fmt(ms: int) -> str:
    return f"{ms / 1000:6.2f}s"


def main() -> None:
    default = Path(__file__).parent / "cena_ponte_comando.json"
    scene_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("build_audio")
    out_dir.mkdir(parents=True, exist_ok=True)

    scene = Scene.from_dict(json.loads(scene_path.read_text(encoding="utf-8")))
    policy = TimingPolicy()

    # UM backend, envolto em TrimmedTTS: remove padding de silêncio antes de medir
    # a duração (protege timing + snap quando o motor for neural). Memoizado, então
    # timing (passagem 2) e render usam exatamente o mesmo áudio.
    backend = TrimmedTTS(FormantTTSBackend(sr=SR))
    timeline = Orquestrador(backend, policy).render_scene(scene)
    clips = {ev.id: backend.synthesize(ev).samples for ev in scene.events}

    # --- Relatório da linha de tempo ---
    print(f"\nCENA: {timeline.scene_id}   ambiencia: {timeline.ambiance}")
    print(f"duracao total: {_fmt(timeline.total_duration_ms)}\n")
    print(f"{'inicio':>7} {'fim':>7} {'pan':>4}  fade_in fade_out  personagem   fala")
    print("-" * 92)
    for p in timeline.placements:
        cut = "  [CORTADA]" if p.hard_cut_ms is not None else ""
        print(
            f"{_fmt(p.start_ms)} {_fmt(p.end_ms)} {p.pan:>4}  "
            f"{p.fade_in_ms:>6}ms {p.fade_out_ms:>6}ms  "
            f"{p.character:<9}  {p.text[:38]}{cut}"
        )
    overlaps = timeline.overlaps()
    if overlaps:
        print("\nsobreposicoes (QA):", ", ".join(f"{a}x{b}={ms}ms" for a, b, ms in overlaps))

    # --- Render nos 3 modos ---
    renderer = TimelineRenderer(sr=SR, policy=policy)
    jobs = [("01_naive.wav", "naive"), ("02_dry.wav", "dry"), ("03_full.wav", "full")]
    print("\nrenderizando:")
    for fname, mode in jobs:
        stereo = renderer.render(timeline, clips, mode=mode)
        path = out_dir / fname
        renderer.write_wav(str(path), stereo)
        peak = float(abs(stereo).max())
        print(f"  {mode:5} -> {path}   ({stereo.shape[1] / SR:.2f}s, pico {peak:.3f})")

    print(f"\nok. arquivos em: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
