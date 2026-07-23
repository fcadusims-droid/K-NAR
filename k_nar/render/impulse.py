"""Geração procedural de Impulse Responses por ambiência.

Cada cena tem uma identidade acústica (`Scene.ambiance`). Em vez de exigir arquivos
de IR gravados, sintetizamos um IR plausível: reflexões iniciais (o "eco metálico"
da nave) + cauda de ruído com decaimento exponencial, filtrada para dar cor ao
espaço. É esse IR que o bus de reverb aplica em TODAS as vozes da cena, unificando-as
no mesmo lugar físico.
"""

from __future__ import annotations

import numpy as np

_RNG = np.random.default_rng(1917)  # determinístico: mesma cena, mesmo espaço


def _one_pole_lowpass(x: np.ndarray, coeff: float) -> np.ndarray:
    """Filtro passa-baixa simples (escurece a cauda). coeff em [0,1)."""
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = coeff * acc + (1.0 - coeff) * x[i]
        y[i] = acc
    return y


def make_impulse_response(name: str, sr: int) -> np.ndarray:
    """Devolve um IR mono float32 para a ambiência dada."""
    presets = {
        # cockpit metálico: cauda curta e brilhante + reflexões próximas e ríspidas
        "cockpit_metalico_eco": dict(rt=0.42, early=(7, 13, 23, 37, 53), early_gain=0.55,
                                     lp=0.15, metallic=True),
        # sala grande: cauda longa e mais escura
        "sala_grande": dict(rt=1.1, early=(19, 37, 61), early_gain=0.35, lp=0.55, metallic=False),
        # corredor: médio, algumas reflexões tardias
        "corredor_estreito": dict(rt=0.6, early=(11, 29, 47, 71), early_gain=0.45, lp=0.35,
                                  metallic=False),
        # GALPÃO VAZIO: cauda longa, eco nítido de reflexões duras (paredes distantes,
        # vazio) — é o "eco na voz" de dois personagens num espaço grande e vazio.
        "galpao_vazio": dict(rt=1.7, early=(29, 53, 83, 121, 167), early_gain=0.6, lp=0.4,
                             metallic=False),
        # catedral: cauda MUITO longa e brilhante (pedra alta)
        "catedral": dict(rt=3.2, early=(41, 79, 131, 197), early_gain=0.45, lp=0.25, metallic=False),
        # caverna: longa, escura e irregular (rocha)
        "caverna": dict(rt=2.4, early=(37, 67, 113, 179, 233), early_gain=0.5, lp=0.7, metallic=False),
        # quarto pequeno: cauda curta e apertada
        "quarto_pequeno": dict(rt=0.28, early=(7, 17, 29), early_gain=0.4, lp=0.5, metallic=False),
        # banheiro: curto, brilhante, com flutter (azulejo)
        "banheiro": dict(rt=0.5, early=(5, 11, 17, 23, 31), early_gain=0.55, lp=0.1, metallic=True),
        # túnel: médio-longo e metálico
        "tunel": dict(rt=1.3, early=(23, 47, 79, 113), early_gain=0.55, lp=0.45, metallic=True),
        # seco: quase sem reverb (IR ~ impulso)
        "seco": dict(rt=0.05, early=(), early_gain=0.0, lp=0.0, metallic=False),
    }
    cfg = presets.get(name, presets["cockpit_metalico_eco"])

    length = max(int(sr * cfg["rt"]), 1)
    t = np.arange(length, dtype=np.float32)

    # Cauda: ruído branco com decaimento exponencial (RT60 ~ rt).
    decay = np.exp(-6.9 * t / length).astype(np.float32)  # ~ -60 dB no fim
    tail = _RNG.standard_normal(length).astype(np.float32) * decay
    if cfg["lp"] > 0:
        tail = _one_pole_lowpass(tail, cfg["lp"])

    ir = np.zeros(length, dtype=np.float32)
    ir[0] = 1.0  # som direto
    for ms in cfg["early"]:
        idx = int(sr * ms / 1000.0)
        if idx < length:
            ir[idx] += cfg["early_gain"] * (0.85 ** cfg["early"].index(ms))
    ir += 0.6 * tail

    if cfg["metallic"]:
        # leve ressonância metálica: soma de alguns "modos" agudos batendo juntos
        for f in (1900.0, 3100.0, 4200.0):
            ir += 0.05 * np.sin(2 * np.pi * f * t / sr) * decay

    # normaliza energia para não estourar no wet
    peak = float(np.max(np.abs(ir)))
    if peak > 0:
        ir = ir / peak
    return ir.astype(np.float32)
