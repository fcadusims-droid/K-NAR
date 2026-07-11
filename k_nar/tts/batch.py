"""Síntese em lote e paralela da PASSAGEM 2.

Segunda metade da resposta de latência: a síntese de cada fala é INDEPENDENTE, então
a passagem 2 é "embaraçosamente paralela". Rodamos todas num pool de threads —
motores nativos (onnx do Piper, torch do XTTS) liberam o GIL durante a inferência,
então o tempo de parede vira ~o da fala mais lenta, não a soma de todas.

Isso mantém o pipeline de duas passagens intacto: sintetiza-se TUDO primeiro (agora
em paralelo e com cache), e só então a passagem 3 (linha de tempo) roda — que é pura
aritmética sobre durações, instantânea, e nunca bloqueia esperando áudio.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from k_nar.models import SpeechEvent
from k_nar.tts.base import RenderedClip, TTSBackend


def synthesize_all(backend: TTSBackend, events: list[SpeechEvent],
                   workers: int = 4) -> dict[str, RenderedClip]:
    """Sintetiza todos os eventos em paralelo. Devolve {event_id: RenderedClip}.

    Com um `CachingTTS` por baixo, falas já sintetizadas voltam do disco na hora;
    só as novas pagam o custo neural — e essas em paralelo.
    """
    if workers <= 1 or len(events) <= 1:
        return {ev.id: backend.synthesize(ev) for ev in events}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(backend.synthesize, events))
    return {ev.id: clip for ev, clip in zip(events, results)}
