"""Forced alignment — fronteiras REAIS de fonema para o corte de interrupção.

O `snap_to_valley` por energia é *fonética-cego*: acha o vale de MENOR energia,
mas isso pode cair no meio de uma vogal sustentada ou numa oclusiva. Foi o degrau
que o teste com áudio real apontou (um corte ficou em 0.93× da média — nem vale,
nem fronteira).

O Piper (VITS) tem um preditor de duração interno e, com `include_alignments`,
EXPÕE quantas amostras cada fonema ocupa no áudio sintetizado. Isso é *forced
alignment de verdade* — o alinhamento do próprio modelo, sem aligner externo
(whisperx/MFA) e sem baixar mais nada.

Este módulo é **dado puro** (stdlib): índices de amostra, sem áudio, sem numpy.
Essa é a virada de acoplamento: como o alinhamento não precisa do sinal, a decisão
do corte SOBE do renderer (que adivinhava por energia) para o Orquestrador, que já
tem o alinhamento e a duração real. A EDL carrega a decisão; o renderer só aplica.
O snap por energia continua como *fallback* auditável quando não há alinhamento
(mock, formante, ou um backend que não exporte fonemas).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Fonemas que representam FRONTEIRA DE PALAVRA (espaço). Cortar aqui é o que soa
# como uma interrupção humana natural: a palavra anterior termina inteira.
_WORD_GAP = {" ", ""}
# Pontuação = pausa prosódica: fronteira ainda MELHOR para cortar que a de palavra.
_PUNCT = {".", ",", ";", ":", "!", "?", "…", "—", "-", "¿", "¡"}
# Marcadores especiais do Piper/espeak (BOS/EOS) — fronteira forte de borda.
_BOUNDARY_MARKS = {"^", "$"}

# Pesos das fronteiras candidatas (maior = melhor lugar para cortar).
_W_PUNCT = 3
_W_WORD = 2
_W_PHONEME = 1


@dataclass(frozen=True)
class PhonemeSpan:
    """Um fonema ocupando [start, end) amostras do clip sintetizado."""

    phoneme: str
    start: int  # amostra inicial (inclusive)
    end: int    # amostra final (exclusive)

    @property
    def is_word_gap(self) -> bool:
        return self.phoneme in _WORD_GAP or self.phoneme in _BOUNDARY_MARKS

    @property
    def is_punct(self) -> bool:
        return self.phoneme in _PUNCT

    @property
    def boundary_weight(self) -> int:
        """Quão bom é cortar NO INÍCIO deste fonema (fim do anterior)."""
        if self.is_punct:
            return _W_PUNCT
        if self.is_word_gap:
            return _W_WORD
        return _W_PHONEME


@dataclass
class Alignment:
    """Alinhamento fonema→amostra de UM clip. Dado puro, sem áudio."""

    spans: list[PhonemeSpan] = field(default_factory=list)
    sample_rate: int = 22050

    @property
    def length(self) -> int:
        return self.spans[-1].end if self.spans else 0

    def __bool__(self) -> bool:
        return bool(self.spans)

    # ------------------------------------------------------------------ #
    #  Construção                                                         #
    # ------------------------------------------------------------------ #
    @classmethod
    def from_piper(cls, phoneme_alignments, sample_rate: int) -> "Alignment":
        """Constrói a partir de `AudioChunk.phoneme_alignments` do Piper.

        Cada item expõe `.phoneme` e `.num_samples`; a soma dos `num_samples`
        particiona o áudio, então basta acumular offsets.
        """
        spans: list[PhonemeSpan] = []
        cursor = 0
        for a in phoneme_alignments:
            ns = int(getattr(a, "num_samples", 0))
            if ns <= 0:
                continue
            ph = str(getattr(a, "phoneme", ""))
            spans.append(PhonemeSpan(ph, cursor, cursor + ns))
            cursor += ns
        return cls(spans=spans, sample_rate=sample_rate)

    # ------------------------------------------------------------------ #
    #  Transformações que ACOMPANHAM as do áudio no pipeline             #
    # ------------------------------------------------------------------ #
    def scaled(self, ratio: float) -> "Alignment":
        """Reamostragem por `ratio` (o pitch-shift do neural.py): escala os índices.

        O `PiperTTSBackend` sintetiza mais lento e reamostra de volta por 1/p para
        subir o pitch; o alinhamento tem de sofrer a mesma escala para continuar
        apontando o mesmo instante acústico.
        """
        if abs(ratio - 1.0) < 1e-9:
            return Alignment(list(self.spans), self.sample_rate)
        spans = [
            PhonemeSpan(s.phoneme, int(round(s.start * ratio)), int(round(s.end * ratio)))
            for s in self.spans
        ]
        return Alignment(spans, self.sample_rate)

    def trimmed(self, lead: int, new_length: int) -> "Alignment":
        """`TrimmedTTS` removeu `lead` amostras do início e cortou em `new_length`.

        Desloca todo o alinhamento por -lead e clampa em [0, new_length], descartando
        fonemas que caíram inteiramente no padding removido.
        """
        out: list[PhonemeSpan] = []
        for s in self.spans:
            ns = max(0, min(s.start - lead, new_length))
            ne = max(0, min(s.end - lead, new_length))
            if ne > ns:
                out.append(PhonemeSpan(s.phoneme, ns, ne))
        return Alignment(out, self.sample_rate)

    # ------------------------------------------------------------------ #
    #  A decisão do corte                                                 #
    # ------------------------------------------------------------------ #
    def boundaries(self) -> list[tuple[int, int]]:
        """(amostra, peso) de cada fronteira candidata ao corte.

        A fronteira fica no INÍCIO de cada fonema (= fim do fonema anterior). O peso
        distingue pontuação > fronteira-de-palavra > fronteira-de-fonema.
        """
        return [(s.start, s.boundary_weight) for s in self.spans if s.start > 0]

    def phoneme_at(self, sample: int) -> str:
        """O fonema que contém `sample` (para diagnóstico: 'caiu no meio de X')."""
        for s in self.spans:
            if s.start <= sample < s.end:
                return s.phoneme
        return "?"

    def snap(self, target: int, window: int, floor: int) -> tuple[int, str]:
        """Desliza `target` (amostra) até a MELHOR fronteira dentro de ±`window`.

        Prefere pontuação, depois fronteira de palavra, depois fronteira de fonema;
        entre candidatos do mesmo peso, o mais próximo do alvo. Nunca corta antes de
        `floor` (mínimo audível decidido pela política). Se não há fronteira na
        janela, devolve o alvo inalterado.

        Retorna (amostra_do_corte, tipo) — tipo ∈ {"pontuacao","palavra","fonema","cru"}.
        """
        if not self.spans:
            return target, "cru"
        lo = max(floor, target - window)
        hi = target + window
        best: tuple[int, int, int] | None = None  # (peso, -distância, amostra)
        for sample, weight in self.boundaries():
            if sample < lo or sample > hi:
                continue
            cand = (weight, -abs(sample - target), sample)
            if best is None or cand > best:
                best = cand
        if best is None:
            return target, "cru"
        weight, _, sample = best
        kind = {_W_PUNCT: "pontuacao", _W_WORD: "palavra"}.get(weight, "fonema")
        return sample, kind
