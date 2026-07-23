#!/usr/bin/env python3
"""Teste A/B REAL da espacialização (Nível 1): o mesmo material renderizado COM e SEM
o "set virtual" de zonas, medido objetivamente e escrito em áudio para ouvir.

O usuário pediu: "faça testes reais para ver se o áudio gerado é melhor com ou sem
isso — se for pior ou igual, não vale a pena manter". Este script responde com
NÚMEROS, não opinião:

  1. OCLUSÃO (cena programática): uma voz no cômodo AO LADO deve perder agudos e
     nível vs. a mesma voz sem espacialização. Mede a energia de alta frequência (HF)
     e o RMS da janela dessa voz nos dois modos.
  2. REVERB SEGUE O POV (história andando pela casa): mede se o "brilho" (centróide
     espectral) varia MAIS entre cômodos no modo espacial (cada cômodo com seu eco)
     do que no flat (um eco só). E confere que não piora o clipping nem engole a fala.

Uso:
    python3 scripts/ab_spatial.py            # roda tudo, escreve os WAV do demo
    python3 scripts/ab_spatial.py --no-audio # só as métricas (não escreve arquivos)

Requer numpy + Piper (models/piper) + sons (sounds/). Sem Piper, cai no formante.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from k_nar import Orquestrador, Scene, SpeechEvent  # noqa: E402
from k_nar.render.renderer import TimelineRenderer  # noqa: E402
from k_nar.space import SceneModel, Zone  # noqa: E402


# --------------------------------------------------------------------------- #
#  Métricas (dado puro sobre a onda)                                          #
# --------------------------------------------------------------------------- #
def _mono(stereo: np.ndarray) -> np.ndarray:
    return stereo.mean(axis=0) if stereo.ndim == 2 else stereo


def hf_ratio(mono: np.ndarray, sr: int, cutoff: float = 3000.0) -> float:
    """Fração da energia espectral ACIMA de `cutoff` (o "brilho"/agudos). A parede/ar
    comem os agudos: menos HF = som mais abafado/distante."""
    if mono.size == 0:
        return 0.0
    spec = np.abs(np.fft.rfft(mono)) ** 2
    freqs = np.fft.rfftfreq(mono.size, 1.0 / sr)
    total = float(spec.sum()) or 1.0
    return float(spec[freqs >= cutoff].sum()) / total


def spectral_centroid(mono: np.ndarray, sr: int) -> float:
    """Centróide espectral (Hz): o "centro de gravidade" do brilho do som."""
    if mono.size == 0:
        return 0.0
    spec = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(mono.size, 1.0 / sr)
    s = float(spec.sum()) or 1.0
    return float((freqs * spec).sum() / s)


def rms_db(mono: np.ndarray) -> float:
    r = float(np.sqrt(np.mean(mono ** 2))) if mono.size else 0.0
    return 20.0 * np.log10(r) if r > 1e-9 else -120.0


def window(stereo: np.ndarray, sr: int, start_ms: int, end_ms: int) -> np.ndarray:
    a = max(0, int(start_ms * sr / 1000))
    b = min(stereo.shape[1], int(end_ms * sr / 1000))
    return _mono(stereo[:, a:b]) if b > a else np.zeros(0, dtype=np.float32)


# --------------------------------------------------------------------------- #
#  Backend de voz (Piper real se houver; senão formante)                      #
# --------------------------------------------------------------------------- #
def _voice(sr_box):
    main = Path("models/piper/pt_BR-faber-medium.onnx")
    if main.exists():
        from k_nar.prosody import ProsodyPolicy
        from k_nar.render.trim import TrimmedTTS
        from k_nar.tts.multivoice import MultiVoiceTTSBackend
        mv = MultiVoiceTTSBackend(default_model=str(main), prosody=ProsodyPolicy())
        sr_box[0] = 22050
        return TrimmedTTS(mv), "piper"
    from k_nar.render.voice import FormantTTSBackend
    sr_box[0] = 24000
    return FormantTTSBackend(sr=24000), "formante"


def _render(scene, scene_model, sr, voice, spatial_narration=False):
    clips = {ev.id: voice.synthesize(ev) for ev in scene.events}
    samples = {eid: c.samples for eid, c in clips.items()}
    tl = Orquestrador(voice, scene_model=scene_model,
                      spatial_narration=spatial_narration).render_scene(scene, clips=clips)
    stereo = TimelineRenderer(sr=sr).render(tl, samples, mode="full")
    return tl, stereo


# --------------------------------------------------------------------------- #
#  TESTE 1 — Oclusão: voz no cômodo ao lado perde agudos e nível              #
# --------------------------------------------------------------------------- #
def test_occlusion(sr, voice) -> bool:
    # sala (ouvinte) — cozinha (vizinha, por uma porta). Duas falas: uma na sala
    # (mesma zona) e uma na cozinha (atrás da parede).
    scene = Scene(id="occ", ambiance="sala_grande", events=[
        SpeechEvent(id="perto", character="A", text="Estou aqui na sala com voce agora."),
        SpeechEvent(id="longe", character="B", text="Estou aqui na sala com voce agora."),
    ])
    model = SceneModel()
    model.add_zone(Zone("sala", space="sala_grande"))
    model.add_zone(Zone("cozinha", space="sala_grande"))  # mesmo reverb: isola a OCLUSÃO
    model.link("sala", "cozinha")
    model.default_zone = "sala"
    model.move_listener("perto", "sala"); model.place_source("perto", "sala")
    model.move_listener("longe", "sala"); model.place_source("longe", "cozinha")  # atrás da parede

    tl_flat, flat = _render(scene, None, sr, voice)
    tl_sp, sp = _render(scene, model, sr, voice)

    def win(tl, stereo, eid):
        p = next(x for x in tl.placements if x.event_id == eid)
        return window(stereo, sr, p.start_ms, p.natural_end_ms)

    far_flat, far_sp = win(tl_flat, flat, "longe"), win(tl_sp, sp, "longe")
    near_flat, near_sp = win(tl_flat, flat, "perto"), win(tl_sp, sp, "perto")

    hf_far_flat, hf_far_sp = hf_ratio(far_flat, sr), hf_ratio(far_sp, sr)
    hf_near_flat, hf_near_sp = hf_ratio(near_flat, sr), hf_ratio(near_sp, sr)
    lvl_far = rms_db(far_sp) - rms_db(far_flat)
    lvl_near = rms_db(near_sp) - rms_db(near_flat)

    print("\n[1] OCLUSÃO — voz no cômodo ao lado (mesma frase nos dois modos)")
    print(f"    voz LONGE  HF(agudos):  flat={hf_far_flat:.3f}  ->  espacial={hf_far_sp:.3f}"
          f"   (queda {100*(1-hf_far_sp/(hf_far_flat or 1)):.0f}%)")
    print(f"    voz LONGE  nível:       {lvl_far:+.1f} dB (espacial vs flat)")
    print(f"    voz PERTO  HF(agudos):  flat={hf_near_flat:.3f}  ->  espacial={hf_near_sp:.3f}"
          f"   (~igual, esperado)")
    print(f"    voz PERTO  nível:       {lvl_near:+.1f} dB")

    occluded = hf_far_sp < hf_far_flat * 0.85 and lvl_far < -1.0
    near_ok = hf_near_sp > hf_far_sp    # a de perto continua mais brilhante que a de longe
    ok = occluded and near_ok
    print(f"    => oclusão {'OK' if occluded else 'FALHOU'}; "
          f"perto>longe em brilho: {'OK' if near_ok else 'FALHOU'}")
    return ok


# --------------------------------------------------------------------------- #
#  TESTE 2 — Reverb segue o POV: a CAUDA (ring-out) muda de cômodo p/ cômodo  #
# --------------------------------------------------------------------------- #
def _tail_ratio(stereo: np.ndarray, sr: int, p, tail_ms: int = 400) -> float:
    """Energia da CAUDA (os `tail_ms` após a voz acabar) sobre a energia da voz. É o
    eco do cômodo ringando: alto num salão vazio, ~0 ao ar livre."""
    body = window(stereo, sr, p.start_ms, p.natural_end_ms)
    tail = window(stereo, sr, p.natural_end_ms, p.natural_end_ms + tail_ms)
    rb = float(np.sqrt(np.mean(body ** 2))) if body.size else 0.0
    rt = float(np.sqrt(np.mean(tail ** 2))) if tail.size else 0.0
    return rt / (rb or 1.0)


def _render_utt(text, listener_space, sr, voice, flat_ambiance):
    """Renderiza UMA fala isolada. Se `listener_space` é dado, monta um mini set (a sala
    + uma zona-fantasma p/ o modelo não ser trivial) e põe o ouvinte nela → reverb do
    cômodo. Senão (flat), usa o reverb global `flat_ambiance`."""
    scene = Scene(id="u", ambiance=flat_ambiance,
                  events=[SpeechEvent(id="u", character="A", text=text)])
    model = None
    if listener_space is not None:
        model = SceneModel()
        model.add_zone(Zone("aqui", space=listener_space))
        model.add_zone(Zone("outra", space="seco"))     # 2ª zona: modelo não-trivial
        model.link("aqui", "outra")
        model.default_zone = "aqui"
        model.move_listener("u", "aqui"); model.place_source("u", "aqui")
    return _render(scene, model, sr, voice)


def test_reverb_follows(sr, voice, write_audio: bool) -> bool:
    txt = "As tabuas rangeram sob as botas naquela noite fria."
    rooms = [("quarto_pequeno", "quarto pequeno"), ("galpao_vazio", "salão vazio"),
             ("seco", "quintal aberto")]

    print("\n[2] REVERB SEGUE O POV — cauda (ring-out) por cômodo, mesma frase")
    tails_sp, tails_flat = [], []
    for space, nome in rooms:
        tl_sp, sp = _render_utt(txt, space, sr, voice, flat_ambiance="seco")
        tl_fl, fl = _render_utt(txt, None, sr, voice, flat_ambiance="sala_grande")
        t_sp = _tail_ratio(sp, sr, tl_sp.placements[0])
        t_fl = _tail_ratio(fl, sr, tl_fl.placements[0])
        tails_sp.append(t_sp); tails_flat.append(t_fl)
        print(f"    {nome:14s}  cauda: flat={t_fl:.3f}   espacial={t_sp:.3f}")

    spread_flat = float(np.std(tails_flat))
    spread_sp = float(np.std(tails_sp))
    print(f"    variação da cauda entre cômodos:  flat={spread_flat:.3f}"
          f"   ->  espacial={spread_sp:.3f}  ({spread_sp/(spread_flat or 1e-6):.1f}x)")

    # História real p/ ouvir (o deliverable): a casa inteira, flat vs espacial.
    from k_nar.pipeline import render_story
    from k_nar.story import load_story
    from k_nar.render import dsp
    story = load_story("examples/casa_de_madeira.md")
    demo_flat = render_story(story, sounds_dir="sounds", spatialize=False)
    demo_sp = render_story(story, sounds_dir="sounds", spatialize=True)
    clip_fl = dsp.clipping_stats(demo_flat.stereo)["clipped_ratio"]
    clip_sp = dsp.clipping_stats(demo_sp.stereo)["clipped_ratio"]
    zones = sorted((demo_sp.script.get("espaco") or {}).get("ouvinte", {}).values())
    print(f"    demo 'A Casa de Madeira': zonas na trilha = {sorted(set(zones))}")
    print(f"    clipping:  flat={clip_fl*100:.2f}%   espacial={clip_sp*100:.2f}%"
          f"    issues espacial={[i.code for i in demo_sp.issues] or 'nenhum'}")

    if write_audio:
        out = Path("scratch_ab"); out.mkdir(exist_ok=True)
        TimelineRenderer(sr=demo_flat.sr).write_wav(str(out / "casa_flat.wav"), demo_flat.stereo)
        TimelineRenderer(sr=demo_sp.sr).write_wav(str(out / "casa_espacial.wav"), demo_sp.stereo)
        print(f"    áudio p/ ouvir: {out}/casa_flat.wav  e  {out}/casa_espacial.wav")

    varies_more = spread_sp > spread_flat * 3.0 and spread_sp > 0.05
    no_regress = clip_sp <= clip_fl + 0.001 and not demo_sp.issues
    print(f"    => reverb varia por cômodo: {'OK' if varies_more else 'FRACO'}; "
          f"sem regressão de mix: {'OK' if no_regress else 'FALHOU'}")
    return varies_more and no_regress


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-audio", action="store_true", help="não escrever os WAV")
    args = ap.parse_args()

    sr_box = [22050]
    voice, kind = _voice(sr_box)
    sr = sr_box[0]
    print(f"Backend de voz: {kind}  (sr={sr})")

    ok1 = test_occlusion(sr, voice)
    ok2 = test_reverb_follows(sr, voice, write_audio=not args.no_audio)

    print("\n" + "=" * 64)
    verdict = ok1 and ok2
    if verdict:
        print("VEREDITO: a espacialização MELHORA o áudio de forma mensurável")
        print("  (oclusão real entre cômodos + reverb que segue o POV, sem regressão).")
        print("  => VALE MANTER (ligada por padrão quando há >=2 cômodos).")
    else:
        print("VEREDITO: sinal fraco/regressão — revisar antes de ligar por padrão.")
    print("=" * 64)
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
