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
  uma ação) e cama ambiental (loopável, baixa, localizada: entra/sai de cena).
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

### Fase 6 — Polimento e escala (em andamento)
* **Diretor de mix** ✅ — `MixPolicy` (`k_nar/mixpolicy.py`): os níveis de bus por
  trilha (fala / narração / SFX / ambiência / música) + a profundidade do ducking numa
  matriz única, no espírito do `TimingPolicy` e do `ProsodyPolicy`. Dois níveis de
  ganho: por evento (Director) e por bus (mixador). O renderer o consome.
* **Música** — a trilha `musica` já é ducada e tem nível no `MixPolicy`; falta só um
  `MusicEvent`/fonte dedicada (uma trilha via `LibrarySfxBackend` já funciona).
* Pendentes (polimento menor): crossfade equal-power em `sobreposicao` longa;
  calibrar mais o `LlamaDirector` (precisa do modelo); `NeuralSfxBackend`; sincronia
  fina SFX↔verbo via forced alignment sobre a narração.

### Fase 7 — "Set virtual" acústico + elenco + pessoa narrativa ✅

A visão do usuário: o motor construir um **modelo da cena** (o "set" — cômodos,
quem está onde, por onde o POV anda) e **derivar** a acústica dele, como áudio de
jogo (o som bate na parede e volta). A decisão consciente foi fazer a versão **por
ZONAS** (leve, autorável, reaproveita o render) e **não** um simulador de física de
raios (caro, frágil e quase inaudível em estéreo) — ver "Riscos honestos".

* **Nível 1 — `SceneModel` (`k_nar/space/`)** ✅: grafo de zonas (cômodo → preset de
  reverb) + adjacência (portas) + onde a fonte e o ouvinte estão a cada evento. Resolve
  um `SpatialCue` por evento — reverb do cômodo do **ouvinte**, distância (mesma zona ×
  outra) e **oclusão** (a parede, via `SpacePolicy`). Dado puro (stdlib): o Orquestrador
  grava na EDL, o renderer aplica **reverb por-evento** (o eco segue o POV) e pula o
  reverb global. O Screenwriter detecta os cômodos na prosa (o POV "anda" pela casa).
* **A/B REAL** ✅ (`scripts/ab_spatial.py`, Piper + ESC-50): a espacialização **melhora**
  de forma mensurável — voz do cômodo ao lado perde ~95% dos agudos e ~11 dB; a cauda
  de reverb varia ~6× mais por cômodo (o quintal aberto fica seco, o salão ecoa), sem
  regressão de clipping/QA. Ligada por padrão quando há 2+ cômodos (`--sem-espaco` desliga).
* **Elenco por aparência (`k_nar/casting.py`)** ✅: infere idade/gênero/timbre dos
  **descritores** na prosa e escolhe a voz (pitch/ritmo) por personagem — o velho grave e
  lento, a menina aguda e ágil. Gênero vem do texto, nunca do nome (não "misgenera").
* **Pessoa narrativa (`k_nar/narrative/person.py`)** ✅: 3ª pessoa = narrador onisciente
  **seco** (fora da cena); 1ª pessoa = a narração É o protagonista (mesma voz, **dentro**
  da cena, leva o reverb do cômodo). Detectada da narração ou fixa no front-matter, com
  dois templates prontos (`examples/template_{primeira,terceira}_pessoa.md`).
* **Refinamentos de mixagem (pós-feedback de audição)** ✅: (a) **qualidade de voz** — o
  reverb por-evento a `wet` fixo abafava a fala ("160p"); agora o `wet` é **por cômodo**
  (pequeno = seco, voz limpa). (b) **nível de SFX por categoria** — foley (passos) senta
  abaixo de um impacto (não vão todos ao mesmo pico). (c) **material** (`MaterialPolicy`)
  — bota em madeira ≠ chinelo em concreto (timbre + nível), p/ qualquer foley. (d)
  **fonte cross-room da prosa** — "da cozinha, ela gritou" põe a voz noutro cômodo
  (oclusão) sem mover o POV. (e) **auto-atribuição em 1ª pessoa** ("gritei" → voz do
  protagonista). Ver `examples/primeira_pessoa_demo.md`.

### Fase 8 — Atuação, acústica de mobília e voz de alta qualidade ✅

Feedback do usuário: (1) todo cômodo fechado ecoava como caverna; (2) as vozes não
atuavam, liam neutro. Além disso, subir a qualidade bruta da voz.

* **Acústica ciente de MOBÍLIA (`Zone.damping`, `PRESET_DAMPING`)** ✅: o cômodo tem um
  reverb POTENCIAL (tamanho) e um AMORTECIMENTO (mobília/uso). Por padrão é **mobiliado
  → seco** (escritório em uso não ecoa); só **vazio/nu/reforma** ecoa; "ecoou" na prosa
  força o eco. O Screenwriter lê móveis vs. vazio; o renderer reduz o wet por `1−damping`.
* **Sistema de ATUAÇÃO (`k_nar/emotion.py` + `narrative/acting.py`)** ✅: `EmotionPolicy`
  (emoção → ritmo/pitch/variância/ganho/pausa, irmã da ProsodyPolicy) + inferência por
  regras (pontuação, léxico de emoção, verbo de fala, **termômetro de cena**, **reação**
  à linha anterior) + **persona** por personagem (temperamento). A emoção compõe com a
  tensão na `ProsodyPolicy.resolve`; as pausas emocionais entram no Orquestrador. A
  narração também atua. O `LlamaDirector` fica como upgrade de inferência.
* **Voz de ALTA qualidade — XTTS-v2 (`k_nar/tts/xtts.py`)** ✅: `--voz xtts` troca o Piper
  (não há voz "high" em pt) pelo XTTS, atrás do mesmo `TTSBackend` — voz por personagem
  via locutor de estúdio + a mesma `EmotionPolicy`. Opt-in (lento, ~s/frase).
* **Entrega sob limite (`scripts/package_audio.py`)** ✅: Opus (metade do MP3 na mesma
  qualidade — 41 min ≈ 17 MB) e, se preciso, divisão em partes cortando no silêncio.
* **Template empírico** ✅: `docs/TEMPLATE.md` reescrito com o que o parser acerta
  (testado); comentários HTML `<!-- -->` agora são removidos da prosa (não são lidos).

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
