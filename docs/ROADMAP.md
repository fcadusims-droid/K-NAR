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

### Fase 2 — Voz por personagem + QA acústico
* Modelos/perfis de voz distintos por personagem atrás do mesmo `TTSBackend`
  (`Protocol`) — sem tocar no Orquestrador.
* Detector automatizado de clipping e de overlaps que engolem palavras (estende o
  `Timeline.overlaps()` que já existe). Vira a rede de segurança ANTES de multiplicar
  as camadas de áudio nas fases seguintes.

### Fase 3 — Generalizar `Event` + Timeline multitrack
* `SpeechEvent` → união `Event` com um campo discriminador; adicionar
  `NarrationEvent` (fala do narrador, reusa 100% do TTS).
* Timeline ganha buses paralelos; o renderer mixa N trilhas. Ainda sem SFX — só
  provar que a EDL suporta narração + diálogo em trilhas separadas. **Baixo risco,
  alta alavancagem**: é o pré-requisito estrutural de tudo que vem depois.

### Fase 4 — Camada Screenwriter (PASSAGEM 0)
`k_nar/narrative/`: prosa crua → grafo de cenas, marcando narração / diálogo / ação
/ ambiência. É o Director "subindo um nível" (antes recebia falas prontas; agora
recebe a história). Schema estrito + fallback por regras (a filosofia de nunca
falhar em silêncio). Entregável: uma história curta → EDL completa com as *cues*
marcadas (ainda sem áudio de SFX).

### Fase 5 — SFX pontual (foley) + ambiência + ducking
* `SfxBackend` (`Protocol`, espelhando `TTSBackend`): `LibrarySfxBackend` (busca em
  biblioteca de samples etiquetada) primeiro, `NeuralSfxBackend` (texto→áudio tipo
  AudioGen/Stable Audio) depois.
* `AmbienceLibrary`: camas ambientais loopáveis por cenário.
* Ducking sidechain no renderer (`pedalboard.Compressor`): ambiência/música afundam
  sob a fala. Foley ancorado ao verbo via o forced alignment da Fase 1.
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
