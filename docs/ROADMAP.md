# Roadmap — de motor de diálogo a motor de áudio narrativo

O K-NAR nasceu como um motor de **performance de diálogo** (orquestrador de duas
passagens, orientado a linha de tempo). O alvo maior é torná-lo um motor de
**áudio narrativo completo**: dada uma história em prosa — cenas, ações, diálogos —
gerar o audiobook dramatizado inteiro, com narração, vozes, efeitos sonoros
pontuais (foley), ambiência e (no futuro) música, tudo num espaço acústico coeso.

## O insight que segura o roadmap

A tese arquitetural do K-NAR não é específica de fala. A **EDL** (Edit Decision
List) e o padrão *"intenção relativa → o código resolve os ms → o DSP renderiza"*
valem para qualquer som. **Um SFX é só mais um evento na linha de tempo**: tem um
início relativo (ancorado a uma ação/fala), uma duração real (medida do sample ou
gerada), um ganho e uma posição estéreo — exatamente o que o `Placement` já modela.

Logo, virar motor narrativo não é reescrever o núcleo; é **generalizar dois pontos**:

1. O modelo de evento deixa de ser só `SpeechEvent` e vira uma união `Event`
   (`Narration` / `Speech` / `Sfx` / `Ambience` / `Music`).
2. A Timeline deixa de ser mono-bus e vira **multitrack com ducking** (a ambiência
   e a música afundam sob a fala via sidechain).

Tudo o que já existe — `snap_to_valley`, forced alignment, crossfade equal-power,
`ProsodyPolicy`, reverb convolutivo — continua valendo. Adicionam-se trilhas
paralelas, não um sistema paralelo.

## Fases

Cada fase entrega algo tocável. As Fases 0–2 endurecem a base de diálogo; as
Fases 3–6 constroem a visão narrativa reaproveitando o que veio antes.

### Fase 0 — Destravar ambiente ✅
Instalar `numpy`/`pedalboard`/`piper`/`onnx`, baixar a voz Piper, e confirmar que
a suíte inteira roda (sem os *skips* de DSP/TTS) e que `render_neural` gera áudio.
Pré-requisito de qualquer validação com áudio real.

### Fase 1 — Forced alignment ✅
Ancorar o corte de interrupção em fronteiras de fonema REAIS (o alinhamento interno
do próprio Piper/VITS via `include_alignments`), com refino acústico numa janela
estreita. Fallback de energia para backends sem fonemas. **Reaproveitado na Fase 5**
para ancorar o foley ao verbo exato da ação. Ver `docs/ARCHITECTURE.md`.

### Fase 2 — Voz por personagem + QA acústico ✅
* `VoiceProfile` + `MultiVoiceTTSBackend`: modelos/perfis de voz distintos por
  personagem atrás do mesmo `TTSBackend` (`Protocol`) — sem tocar no Orquestrador.
  Suporte a `speaker_id` (modelos VITS multi-locutor). Demo com faber+jeff reais.
* `k_nar/qa.py`: detector automatizado de clipping/pico (`check_mix`) e de overlaps
  que engolem palavras / cortes agressivos / cruzamentos inesperados (`check_timeline`).
  CI roda a suíte a cada push/PR. Rede de segurança ANTES de multiplicar as camadas.

### Fase 3 — Generalizar `Event` + Timeline multitrack ✅
* `SpeechEvent` ganha discriminador `Track`; `NarrationEvent` (fala do narrador,
  reusa 100% do TTS) entra na trilha de narração; `build_event` faz o dispatch a
  partir do JSON (retrocompatível).
* `Placement.track` + `renderer._render_tracks`/`_combine_tracks`: a EDL suporta
  narração + diálogo em trilhas separadas; o renderer mixa por trilha e combina (soma
  hoje, ducking na Fase 5). Demo: `examples/narrated_scene.py`.

### Fase 4 — Camada Screenwriter (PASSAGEM 0) ✅
`k_nar/narrative/`: `RuleBasedScreenwriter` segmenta a prosa (aspas → diálogo com
locutor + deixa; resto → narração; verbos/substantivos de ação → gatilhos de SFX).
O `Director` foi estendido p/ consumir `elementos` (narração + diálogo) e a deixa
calibra a tensão. Guard cross-track no Orquestrador: interrupção/sobreposição só
valem dentro da mesma trilha (ninguém interrompe o narrador). Cadeia completa em
`examples/story_to_audio.py`: história `.txt` → áudio narrado multitrack. Os gatilhos
de ação já saem prontos como sementes p/ o SFX da Fase 5.

### Fase 5 — SFX/foley + ambiência + ducking (ÁUDIO REAL primeiro) ✅

O princípio: **áudio real da biblioteca, não geração neural** (mais barato e melhor
para foley/ambiência). O motor lê a cena, busca o som por tag e o edita para seguir
o pacing — mixado profissionalmente para um som não estragar o outro.

* `SfxBackend` (`Protocol`, espelhando `TTSBackend`): `LibrarySfxBackend` (busca real
  em biblioteca de samples etiquetada por tag) é o baseline; `ProceduralSfxBackend`
  (síntese determinística, sem arquivos) é o stand-in runnable — como o `FormantTTS`
  é para a voz; `NeuralSfxBackend` (texto→áudio) fica como reserva distante.
* `SfxEvent` / `AmbienceEvent`: SFX pontual (duração real medida do sample, ancorado a
  uma ação) e cama ambiental (loopável, cobre a cena, baixa).
* **Ducking sidechain** no `_combine_tracks`: ambiência/SFX/música afundam sob a fala
  (envelope da trilha de voz) e voltam quando ela pára. É a mixagem profissional que
  impede a cacofonia.
* **Narrador OPCIONAL** (modo radiodrama): o Screenwriter classifica cada frase em
  diálogo / narração falada / **deixa de som** / ambiência. Descrição sensorial
  ("passos numa poça d'água") vira SFX, NÃO é lida pelo narrador. Com `narrator=False`,
  a história é contada só por vozes + sons.
* **Diálogo reativo ao som**: um SFX é um evento com duração real, então a fala pode
  ser ancorada a ele ("entra após o tiro", "grita durante a explosão") — a mesma tese
  de duas passagens (intenção relativa → ms reais). A *reação* é feita no render
  offline (soa reativo ao ouvinte); streaming ao vivo fica fora de escopo.
* **Aqui o motor vira o que a visão pede**: história em texto → audiobook com sons.

### Fase 6 — Polimento e escala
Música/trilha; crossfade equal-power em `sobreposicao` longa; calibrar o
`LlamaDirector`; e um "diretor de mix" — os níveis relativos de narração / fala /
SFX / ambiência como mais uma matriz de política, no espírito do `TimingPolicy` e
da `ProsodyPolicy`.

## Caminho crítico

Não pular direto para SFX. A ordem **0 → 1 → 3** é o caminho crítico: forced
alignment (1) e a generalização do evento (3) são os pré-requisitos que tornam o
SFX (5) *fácil* em vez de um sistema paralelo bagunçado. As Fases 2 e 4 podem correr
em paralelo.

## Riscos honestos das fases narrativas

1. **Segmentação de prosa é frágil** — separar narração/diálogo/ação e inferir quais
   ações merecem som é um trabalho de LLM mais ambíguo que classificar tensão. Exige
   schema estrito + fallback auditável.
2. **Sincronia SFX↔ação** — o som tem de cair no verbo, não no fim da frase (é forced
   alignment de novo, agora sobre a narração).
3. **Cacofonia / mix** — sem ducking disciplinado, a ambiência engole a fala; "mais
   camadas" pode piorar o resultado se o mix não for rígido.
4. **Fonte de SFX** — biblioteca (licenciamento + curadoria) vs neural (latência +
   qualidade instável). Provavelmente os dois: library como baseline, neural para o
   que faltar.
