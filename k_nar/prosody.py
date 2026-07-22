"""ProsodyPolicy — a matriz que traduz TENSÃO em manipuladores acústicos reais.

O ponto cego que isto resolve: o Piper é emocionalmente inerte. Ele não muda a
entonação porque o JSON diz "cena dramática"; a onda que ele gera ignora a emoção.
Logo, TODA a expressividade precisa ser sintetizada por nós — e de forma consistente
entre o que o TTS gera, o que o Orquestrador corta e o que o DSP processa. Senão o
áudio soa "descolado": corte agressivo sobre uma fala que o motor pronunciou plana.

Esta política é a fonte única: um escalar de tensão (0..1) se abre em rate (velocidade),
pitch (agudo/grave), variância prosódica e ganho (dinâmica). O backend neural usa
rate/pitch/variância; o renderer usa o ganho. Ambos leem daqui, então concordam.

Como o Piper não tem style embedding zero-shot, injetamos a flutuação por 3 alavancas:
  1. length_scale (nativa)   -> comprime/alonga a fala (ritmo);
  2. pitch por reamostragem  -> agudo (agitação) / grave (sombrio), sem mudar a duração;
  3. noise_w/noise_scale     -> variabilidade de entonação (mais viva sob tensão);
  + ganho (no DSP)           -> contraste de dinâmica (sussurro vs grito).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from k_nar.models import TENSION_LABELS


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


@dataclass
class Prosody:
    """Bundle acústico resolvido para UMA fala."""

    length_scale: float    # multiplicador de duração do Piper (>1 lento, <1 rápido)
    noise_scale: float
    noise_w: float
    pitch_semitones: float
    gain_db: float


@dataclass
class ProsodyPolicy:
    # Âncoras interpoladas por tensão (0 = calmo, 1 = extremo).
    # Ritmo: tensão sobe -> fala acelera (comprime); calmo -> arrasta.
    length_scale_calm: float = 1.16
    length_scale_tense: float = 0.84
    # Variabilidade de entonação: mais viva sob tensão.
    noise_w_calm: float = 0.6
    noise_w_tense: float = 1.0
    noise_scale_calm: float = 0.85
    noise_scale_tense: float = 1.05
    # Pitch (semitons): grave/sombrio quando calmo, agudo/agitado quando tenso.
    pitch_calm: float = -2.0
    pitch_tense: float = 3.0
    # Dinâmica (ganho no mix): calmo mais baixo, tenso mais alto.
    gain_calm_db: float = -4.5
    gain_tense_db: float = 2.0
    # Bônus: deslocamento fixo de pitch por personagem — dá timbres distintos a
    # partir de um único modelo mono-locutor (não substitui vozes reais, mas ajuda).
    character_pitch: dict[str, float] = field(default_factory=dict)
    character_pitch_spread: float = 2.0  # semitons de separação por índice de personagem

    _char_order: dict[str, int] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------ #
    def resolve(self, tension: float, rate: float = 1.0, character: str = "") -> Prosody:
        t = _clamp(float(tension), 0.0, 1.0)
        char_pitch = self._character_pitch(character)
        return Prosody(
            length_scale=_lerp(self.length_scale_calm, self.length_scale_tense, t) / max(rate, 0.1),
            noise_scale=_lerp(self.noise_scale_calm, self.noise_scale_tense, t),
            noise_w=_lerp(self.noise_w_calm, self.noise_w_tense, t),
            pitch_semitones=_lerp(self.pitch_calm, self.pitch_tense, t) + char_pitch,
            gain_db=_lerp(self.gain_calm_db, self.gain_tense_db, t),
        )

    def _character_pitch(self, character: str) -> float:
        if not character:
            return 0.0
        if character in self.character_pitch:
            return self.character_pitch[character]
        # atribui deslocamentos alternados (-, +, --, ++, ...) por ordem de aparição
        if character not in self._char_order:
            self._char_order[character] = len(self._char_order)
        idx = self._char_order[character]
        step = (idx + 1) // 2 + 1
        sign = -1 if idx % 2 == 0 else 1
        return sign * step * self.character_pitch_spread * 0.5

    # tensão pode chegar como rótulo ou número
    @staticmethod
    def tension_scalar(value) -> float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return _clamp(float(value), 0.0, 1.0)
        return TENSION_LABELS.get(str(value).strip().lower(), 0.0)
