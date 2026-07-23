"""EmotionPolicy — a matriz EMOÇÃO → atuação acústica (irmã da ProsodyPolicy).

O ponto cego que isto resolve: hoje a única alavanca de expressividade é a "tensão"
(um eixo de excitação). Duas falas com a mesma tensão soam iguais, mesmo que uma seja
de MEDO (aguda, trêmula, contida) e a outra de RAIVA (grave, forte, alta). O Piper é
surdo à emoção, então TODA a atuação tem de ser sintetizada por nós.

Esta política dá a cada emoção um "gesto vocal": um deslocamento de ritmo, pitch,
variação de entonação, ganho e pausas, aplicado POR CIMA da prosódia de tensão. É o
mesmo espírito de duas passagens — o Director/LLM diz a INTENÇÃO (emoção + intensidade),
e esta matriz resolve os manipuladores. Afinar a atuação do drama = mexer só aqui.
"""

from __future__ import annotations

from dataclasses import dataclass

# Emoções canônicas. `neutro` é o repouso; as demais são "gestos" sobre ele.
NEUTRO = "neutro"
EMOTIONS = (
    NEUTRO, "medo", "raiva", "alegria", "tristeza", "suspense", "urgencia",
    "ternura", "ironia", "cansaco", "ordem", "suplica", "alivio", "surpresa",
)

_ALIASES = {
    "fear": "medo", "anger": "raiva", "angry": "raiva", "joy": "alegria",
    "happy": "alegria", "sadness": "tristeza", "sad": "tristeza", "tense": "suspense",
    "suspense": "suspense", "urgent": "urgencia", "tender": "ternura",
    "irony": "ironia", "ironic": "ironia", "weary": "cansaco", "tired": "cansaco",
    "command": "ordem", "order": "ordem", "plea": "suplica", "pleading": "suplica",
    "relief": "alivio", "surprise": "surpresa", "medo_panico": "medo",
}


@dataclass(frozen=True)
class EmotionShift:
    """O gesto vocal de uma emoção (na intensidade 1.0). Deltas relativos.

    `arousal` é um PISO para o eixo de tensão (uma fala de urgência já entra tensa,
    mesmo sem pontuação). Os demais campos ajustam a prosódia de tensão já resolvida.
    """

    arousal: float = 0.2       # piso de excitação (0..1) que a emoção implica
    rate_mult: float = 1.0     # multiplica o length_scale invertido (>1 = mais rápido)
    pitch_semitones: float = 0.0
    variance_mult: float = 1.0  # multiplica noise_scale/noise_w (entonação viva/trêmula)
    gain_db: float = 0.0
    pause_before_ms: int = 0   # micro-pausa antes (respiro/hesitação) — usado na Fase B2
    pause_after_ms: int = 0


@dataclass
class EmotionPolicy:
    # emoção → gesto na intensidade máxima. Valores calibrados p/ serem audíveis sem
    # virar caricatura (o teto de naturalidade é o próprio Piper).
    shifts: dict = None  # type: ignore

    def __post_init__(self):
        if self.shifts is None:
            self.shifts = {
                NEUTRO:     EmotionShift(0.20, 1.00,  0.0, 1.00,  0.0,   0,   0),
                "medo":     EmotionShift(0.75, 1.12,  2.0, 1.35, -1.0,  60,   0),
                "raiva":    EmotionShift(0.85, 1.08, -1.0, 1.20,  3.0,   0,  40),
                "alegria":  EmotionShift(0.55, 1.06,  2.0, 1.25,  1.0,   0,   0),
                "tristeza": EmotionShift(0.25, 0.90, -2.0, 0.85, -3.0,   0, 130),
                "suspense": EmotionShift(0.55, 0.93, -0.5, 0.95, -1.5,  90,   0),
                "urgencia": EmotionShift(0.90, 1.18,  1.5, 1.15,  2.0,   0,   0),
                "ternura":  EmotionShift(0.25, 0.95,  0.5, 0.90, -2.5,  40,   0),
                "ironia":   EmotionShift(0.35, 0.96,  0.5, 1.10,  0.0,  40,  40),
                "cansaco":  EmotionShift(0.20, 0.88, -1.5, 0.80, -2.5,   0, 110),
                "ordem":    EmotionShift(0.80, 1.04, -0.5, 1.05,  3.0,   0,  60),
                "suplica":  EmotionShift(0.70, 1.05,  2.5, 1.30,  0.0,  50,   0),
                "alivio":   EmotionShift(0.30, 0.94,  0.0, 0.95, -1.0,  70,   0),
                "surpresa": EmotionShift(0.80, 1.10,  3.0, 1.30,  2.0,  40,   0),
            }

    @staticmethod
    def canonical(emotion: str) -> str:
        key = str(emotion or NEUTRO).strip().lower()
        key = _ALIASES.get(key, key)
        return key

    def resolve(self, emotion: str, intensity: float = 1.0) -> EmotionShift:
        """Gesto vocal escalado pela intensidade (0..1). Neutro/desconhecido = repouso.

        Interpola cada delta entre o repouso (neutro) e o gesto pleno; a intensidade é a
        fração do gesto que se realiza."""
        key = self.canonical(emotion)
        base = self.shifts.get(key)
        if base is None or key == NEUTRO:
            return self.shifts[NEUTRO]
        t = max(0.0, min(1.0, float(intensity)))
        return EmotionShift(
            arousal=base.arousal * t,
            rate_mult=1.0 + (base.rate_mult - 1.0) * t,
            pitch_semitones=base.pitch_semitones * t,
            variance_mult=1.0 + (base.variance_mult - 1.0) * t,
            gain_db=base.gain_db * t,
            pause_before_ms=int(base.pause_before_ms * t),
            pause_after_ms=int(base.pause_after_ms * t),
        )
