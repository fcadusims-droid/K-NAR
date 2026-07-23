# Arquitetura — K-NAR

Motor de áudio drama autônomo, **orientado a linha de tempo** (não a arquivos
isolados). O texto gera *metadados de tempo e performance*; o áudio é renderizado
depois, num espaço acústico virtual coeso.

## A dependência circular (e como ela é resolvida)

O problema que trava a ingenuidade: para montar a cena preciso saber *quando*
cada fala entra — mas o "quando" (em segundos) só existe **depois** de sintetizar
o áudio e medir sua duração. E se eu deixar o LLM chutar segundos, ele erra, e o
ritmo fica mecânico.

A solução é separar **intenção** de **alocação temporal** em duas passagens:

```
[PASSAGEM 1: LLM / Diretor de Palco]
    Cospe TEXTO + metadados RELATIVOS
    (tensao, agressividade da interrupcao, tipo de pausa) — nunca segundos.
            |
            v
[PASSAGEM 2: TTS agnostico]
    Sintetiza cada fala "seca" e MEDE a duracao real (duration_ms).
            |
            v
[PASSAGEM 3: Orquestrador]
    Cruza metadado relativo x duracao real -> Timeline (EDL, dados puros).
            |
            v
[PASSAGEM 4: Environment DSP]  (implementado)
    Reverb convolutivo (IR por cena) + panning + mix multitrack -> audio final coeso.
```

> Nota: este diagrama é o núcleo original (só diálogo). O motor hoje tem também a
> PASSAGEM 0 (Screenwriter: prosa → roteiro) e trilhas de narração/SFX. Ver as seções
> "Camada Screenwriter" e "Generalização para áudio narrativo" abaixo, e `docs/ROADMAP.md`.

> A intenção dramática (agressividade `0.25`) vem do LLM. A **matemática dos
> milissegundos** é resolvida pelo código, já sabendo a duração real. Assim, se a
> fala anterior dura 2s ou 4s, o corte da interrupção é proporcional e natural —
> sem o LLM precisar saber nada de áudio.

## Componentes (o que já existe neste MVP)

| Módulo | Papel |
|---|---|
| `k_nar/models.py` | Schema da PASSAGEM 1. `Scene`/`SpeechEvent` só carregam intenção relativa. `from_dict` lê o JSON do LLM (em PT-BR). |
| `k_nar/tts/base.py` | `TTSBackend` (Protocol agnóstico) + `RenderedClip` (com o `duration_ms` real). |
| `k_nar/tts/mock.py` | `MockTTSBackend` determinístico, sem áudio — permite testar a lógica 100% offline. |
| `k_nar/timeline.py` | **A matriz** (`TimingPolicy`): único lugar com números de ritmo. Traduz relativo→ms com guardas de inteligibilidade. Estruturas `Placement`/`Timeline` (EDL). |
| `k_nar/orchestrator.py` | `Orquestrador`: roda as passagens 2 e 3 e devolve a `Timeline`. |

## Decisões de acoplamento

1. **O core não toca em áudio.** O Orquestrador devolve uma `Timeline` de dados
   puros (uma Edit Decision List). Renderizar é responsabilidade de outra camada.
   Consequência: a lógica de ritmo roda com **stdlib puro** e é totalmente testável.
2. **TTS é um `Protocol`.** XTTS local, API paga ou mock — todos satisfazem o mesmo
   contrato. Trocar o motor de voz não muda uma linha do Orquestrador.
3. **Toda constante de tempo vive no `TimingPolicy`.** Afinar o "feeling" do drama
   inteiro = ajustar um objeto. Um `TimingPolicy` diferente = um "estilo de direção".

## A matriz de tradução (`TimingPolicy`)

| Metadado relativo (LLM) | Tradução | Onde |
|---|---|---|
| `saida.pausa`: curta/media/longa | 200 / 550 / 1100 ms | `dramatic_pause_ms` |
| `voz.tensao`: "alta"/"extrema"/número | escalar 0..1 | `resolve_tension` |
| `entrada.agressividade` (interrupção) | corta `agg` da duração real do anterior | `interruption_start_within_prev` |
| — guarda de inteligibilidade — | anterior sempre audível ≥ 400ms ou ≥ 35% | `min_audible_*` |

## Tipos de entrada (`EntryType`)

- **`sequencial`** — entra após o anterior + pausa dramática.
- **`interrupcao`** — corta o final do anterior (`hard_cut_ms` marca onde o
  renderer deve cortar/duckar a fala interrompida).
- **`sobreposicao`** — fala simultânea; ninguém é cortado, as vozes coexistem.

## Camada DSP (Environment) — implementada

A EDL deixou de ser "puramente matemática": ela **carrega os envelopes de
atenuação** decididos pelo Orquestrador (`fade_in_ms`, `fade_out_ms`,
`cut_snap_window_ms`). O renderer só *aplica* — não adivinha curvas. Isso fecha o
ponto cego do corte frio.

| Módulo | Papel |
|---|---|
| `k_nar/render/dsp.py` | Fades raised-cosine (anti-clique), pan equal-power, **snap ao vale de energia**, convolução via FFT, normalização. |
| `k_nar/render/impulse.py` | IR procedural por ambiência (o "eco metálico" da nave). |
| `k_nar/render/voice.py` | `FormantTTSBackend`: voz sintética por formantes (não-verbal), determinística — alimenta timing e render com o mesmo áudio. |
| `k_nar/render/renderer.py` | `TimelineRenderer`: EDL + clips → mix estéreo. Modos `naive`/`dry`/`full` para A/B. Master via pedalboard (passa-alta + limiter). |
| `k_nar/schema.py` | Validador **estrito** do JSON do LLM (recusa fallback silencioso). |

## Camada Director (PASSAGEM 1) — implementada

Transforma roteiro cru (`personagem` + `texto`) no JSON de metadados relativos que
o Orquestrador consome. Mantém o LLM como *classificador*, não como gerador de
segundos (a "alternativa viável"): ele só decide tensão/entrada/pausa por fala; a
montagem, os pans e a validação estrita ficam no código.

| Módulo | Papel |
|---|---|
| `k_nar/director/base.py` | `BaseDirector`: monta o JSON da cena a partir de decisões por fala; valida no `schema`. |
| `k_nar/director/rules.py` | `RuleBasedDirector`: heurística (pontuação + palavras-gatilho). Sem modelo, determinístico. Baseline e fallback. |
| `k_nar/director/llama.py` | `LlamaDirector`: LLM local (GGUF via `llama-cpp-python`). Classifica por fala; campo inválido cai na regra (fallback auditável, nunca silencioso). |

Pipeline completo: `roteiro → Director → Orquestrador → Renderer → áudio`
(ver `examples/direct_and_render.py`). O LLM padrão é **Qwen2.5-1.5B-Instruct**
(Q4_K_M, ~1.1GB, CPU), instalado por `scripts/setup.sh --llm`.

## TTS neural real + latência (implementado)

O mock/formante foi substituível por voz neural de verdade (`PiperTTSBackend`,
onnx/CPU): fonemas reais — plosivas, fricativas, respiração, prosódia intrínseca.
Isso expõe o pipeline às condições que o mock mascarava.

**Resposta à latência do TTS** (como não deixar a passagem 2 lenta travar o fluxo):

| Peça | Mecanismo |
|---|---|
| `tts/cache.py::CachingTTS` | Cache em disco endereçado por conteúdo (hash de motor+voz+texto+prosódia). Iterar timeline/DSP não re-sintetiza nada. Medido: 0.40s → **0.01s** na 2ª execução. |
| `tts/batch.py::synthesize_all` | Passagem 2 em pool de threads (onnx/torch liberam o GIL). Tempo de parede ≈ fala mais lenta, não a soma. |
| `Orquestrador.render_scene(scene, clips=...)` | Aceita clips pré-sintetizados: síntese (lenta, cacheada, paralela) desacoplada da timeline (pura, instantânea). |

O pipeline de duas passagens é, na prática, "sintetize-tudo-em-lote → arranje": o
lote é onde vivem cache e paralelismo; a timeline nunca bloqueia esperando áudio.

### O que o áudio real revelou (o mock escondia)

O `snap_to_valley`, rodado sobre voz Piper real, mostrou que o alvo de corte
**puramente matemático cai no meio de um fonema** (energia 2.4–3.9× a média — validando
a crítica de que a proporção sozinha é fonética-cega). O snap de energia resgata a
maioria (ex.: 3.9× → 0.18× num vale limpo, deslocando ~36ms), mas nem sempre acha um
vale bom (um caso ficou em 0.93×). Conclusão medida: o snap faz trabalho essencial,
e o degrau final é forced alignment sobre fonemas reais. Ver `examples/render_neural.py`.

## Mapeamento de Expressividade (implementado)

O Piper é **emocionalmente inerte**: a onda que ele gera ignora a semântica da
cena. Logo, a atuação não pode vir do motor — tem de ser sintetizada por nós, e de
forma **consistente** entre síntese, corte e DSP (senão o áudio fica "descolado":
corte agressivo sobre uma fala pronunciada plana).

`k_nar/prosody.py::ProsodyPolicy` é a fonte única: um escalar de tensão (0..1) se
abre em manipuladores acústicos reais. Como o Piper não tem *style embedding*
zero-shot, a flutuação entra por 3 alavancas + 1 no DSP:

| Alavanca | Onde | Efeito da tensão (medido, frase fixa) |
|---|---|---|
| `length_scale` (nativa Piper) | `tts/neural.py` | ritmo: baixa 3332ms → extrema 2720ms |
| pitch por reamostragem | `tts/neural.py` + `dsp.resample_linear` | centroide 2486Hz → 2785Hz (mais agudo) |
| `noise_w`/`noise_scale` (nativa) | `tts/neural.py` | variabilidade de entonação sob tensão |
| ganho de dinâmica (dB) | `Placement.gain_db` → `renderer` | −3.5dB → +2.0dB (sussurro vs grito) |

O **pitch shift sem phase vocoder**: sintetiza-se a fala mais lenta (`length_scale × p`)
e reamostra-se de volta (`1/p`), subindo o pitch em `p` sem mudar a duração-alvo —
aproveitando o time-stretch neural do próprio Piper. Bônus: um deslocamento fixo de
pitch por personagem dá timbres distintos a partir de um modelo mono-locutor.

**Consistência**: `PiperTTSBackend` e `Orquestrador` recebem a MESMA `ProsodyPolicy`.
O pitch/rate que o TTS imprime na onda e o ganho que a EDL carrega vêm da mesma
matriz — a emoção move a onda, o corte e o mix juntos.

### Desachatar o Diretor

O `LlamaDirector` saturava tudo em "alta" (1.5B tende ao extremo). O few-shot em
`director/llama.py` ancora a escala com exemplos de contraste (exposição=baixa,
hesitação=baixa+pausa longa, grito=extrema), instruindo que a maioria das falas é
media/baixa. Resultado: variação real chega ao `schema` — pré-requisito para o
Mapeamento de Expressividade ter o que traduzir.

## Refinamentos de DSP para o áudio neural (implementados)

Preparam o terreno antes de plugar o XTTS, cuja saída é "caótica":

* **Trim de silêncio** (`dsp.trim_silence` + `render/trim.py::TrimmedTTS`): remove o
  padding que motores neurais injetam nas bordas, ANTES de medir a duração. Sem
  isso, o tempo morto corromperia a proporção da interrupção e travaria o
  `snap_to_valley` no silêncio artificial. `TrimmedTTS` envolve qualquer backend.
* **Crossfade equal-power** (`dsp.fade_window(curve="equal_power")`): no ponto de
  interrupção a voz anterior afunda (cos) exatamente sobre a subida (sin) da nova,
  mantendo potência somada constante (0 dB) — no lugar da soma linear `+`, que
  estoura o teto (medido: pico 1.27 → 0.90) e causa cancelamento de fase.

### Respostas às três críticas ao modelo matemático puro

1. **Clique no corte frio** → o Orquestrador emite fades na EDL; o renderer aplica
   fade raised-cosine em toda borda e no ponto de corte. Medido: o maior salto
   amostra-a-amostra (o clique) cai ~18× do modo `naive` para o `dry`.
2. **Loader tolerante é perigoso na fronteira com IA** → `schema.validate_scene`
   recusa rótulos/tipos fora do contrato e lista todos os erros. O loader tolerante
   continua para ergonomia/testes; a validação estrita é o portão de produção.
3. **Guarda "400ms/35%" é fonética-cega** → `snap_to_valley` desliza o corte até o
   vale de energia mais próximo (silêncio entre fonemas) dentro de uma janela de
   tolerância decidida pela política. É um stand-in leve de *forced alignment*:
   corte proporcional escolhido pelo Orquestrador + ajuste acústico fino no renderer.

## Forced alignment no corte de interrupção (implementado)

O degrau que o áudio real apontou. O Piper (VITS) tem um preditor de duração
interno e, com `include_alignments`, EXPÕE quantas amostras cada fonema ocupa —
*forced alignment de verdade*, do próprio modelo, sem aligner externo (whisperx/MFA)
e sem baixar mais nada. Só precisa do pacote `onnx` (patch do grafo em memória).

O achado de acoplamento: como o alinhamento é **dado puro** (índices de amostra, sem
áudio), a decisão do corte SOBE do renderer (que adivinhava por energia) para o
**Orquestrador**, que já tem o alinhamento e a duração real. A EDL carrega a decisão.

| Módulo | Papel |
|---|---|
| `k_nar/align.py` | `Alignment`/`PhonemeSpan`: fronteiras fonema→amostra, stdlib puro. Transforma-se junto do áudio (`scaled` p/ o pitch-shift, `trimmed` p/ o trim de silêncio) e faz o `snap` à melhor fronteira (pontuação > palavra > fonema). |
| `tts/neural.py` | `PiperTTSBackend` carrega com `include_alignments`, coleta os fonemas dos chunks e escala pelo pitch-shift. |
| `orchestrator.py::_resolve_cut` | ancora o corte na fronteira LINGUÍSTICA via `Alignment.snap`; sem alinhamento, cai no fallback de energia (auditável). |

**Híbrido linguístico + acústico** (validado por medição no faber-medium): o
alinhamento do VITS é fiel ao áudio (offset ~0ms), MAS fronteiras palavra-a-palavra
vozeadas ("não‧deve") caem em energia alta — porém sempre há um micro-vale a ≤30ms.
Então: o Orquestrador ancora na **fronteira** (janela larga, `Alignment.snap`) e o
renderer só desliza numa **janela estreita** (`cut_refine_window_ms`, ~30ms) até o
instante acusticamente limpo. Cada sinal no que é melhor — o corte final fica numa
fronteira de palavra REAL *e* num vale de energia. O snap de energia de janela larga
vira o fallback para backends que não exportam fonemas (mock/formante). Ver o A/B em
`examples/render_neural.py` (alvo cru → energia larga → fronteira → refino final).

## Voz distinta por personagem + QA acústico (implementado)

Voz real por personagem (não só o pitch-shift sobre um locutor único) e a rede de
segurança que precede as camadas narrativas.

| Módulo | Papel |
|---|---|
| `tts/multivoice.py` | `VoiceProfile` (modelo próprio / `speaker_id` / pitch / ritmo por personagem) + `MultiVoiceTTSBackend`: roteia cada fala para o backend Piper certo, cacheando UM modelo por (arquivo, locutor). Satisfaz `TTSBackend` — o Orquestrador não muda. |
| `tts/neural.py` | `PiperTTSBackend` aceita `speaker_id` (modelos VITS multi-locutor). |
| `k_nar/qa.py` | `check_timeline` (EDL, stdlib): sobreposição que engole palavra, corte agressivo demais, cruzamento sequencial inesperado. `check_mix` (a partir de `dsp.clipping_stats`): clipping/pico perigoso. `format_report` p/ CI. |
| `render/dsp.py::clipping_stats` | mede pico e amostras clipadas (dado puro p/ o QA decidir sem numpy). |

`examples/multivoice_qa.py` roteia Alien A→faber e Alien B→jeff (dois modelos PT-BR
distintos, timbres reais) e imprime o relatório de QA. Vozes por `scripts/download_piper.sh [voz]`.

A CI (`.github/workflows/tests.yml`) roda a suíte a cada push/PR (usa mock/formante,
sem baixar modelos) — o QA da EDL e do mix vira portão automatizado.

## Generalização para áudio narrativo: `Event` + Timeline multitrack (implementado)

A virada de "motor de diálogo" para "motor de áudio narrativo". O modelo de evento
deixa de ser só `SpeechEvent`: ganha um **discriminador de trilha** (`Track`) e um
segundo tipo, `NarrationEvent` (a voz do narrador — mesmo TTS, outra trilha).

| Peça | Papel |
|---|---|
| `models.Track` | enum de bus: `dialogo`/`narracao`/`sfx`/`ambiencia`/`musica`. O discriminador que separa os eventos no mix. |
| `models.NarrationEvent` | fala do narrador; mesma interface de duck-typing que `SpeechEvent` (o Orquestrador trata os dois no mesmo laço), só o `.track` difere. Entra sempre sequencial. |
| `models.build_event` | dispatcher: lê `tipo_evento` (ou `personagem: "Narrador"`) e constrói o evento certo. Retrocompatível: sem discriminador = diálogo. |
| `Placement.track` / `Timeline.to_dict` | a EDL carrega a trilha de cada evento. |
| `renderer._render_tracks`/`_combine_tracks` | mixa um bed por trilha e os combina. Hoje soma simples (idêntico ao mono-bus); é o ponto onde o **ducking** entra na Fase 5, sem tocar no resto. |
| `schema` | valida `tipo_evento` e dispensa `personagem` na narração (mantém estrito no diálogo). |

Narração e diálogo compartilham o cursor temporal (num audiobook eles se alternam,
não se sobrepõem); o `.track` só decide o bus de render/pan/ducking. Ver
`examples/narrated_scene.py` (narrador→jeff, personagens→faber, EDL em 2 trilhas).

## Camada Screenwriter — PASSAGEM 0 (implementado)

A entrada do motor deixa de ser "falas prontas" e passa a ser a HISTÓRIA em prosa.

| Peça | Papel |
|---|---|
| `narrative/screenwriter.py` | `RuleBasedScreenwriter`: mascara as aspas (a pontuação dentro da fala não corta a frase errada), segmenta em narração/diálogo, extrai locutor + **deixa** (verbo de fala) da atribuição, e detecta **gatilhos de ação** (rangeu→`porta_range`, explodiu→`explosao`) como sementes de SFX. Baseline determinístico; um `LlamaScreenwriter` cobriria os casos difíceis reusando o mesmo contrato. |
| `director/base.py` | consome `elementos` (narração + diálogo) além do formato antigo `falas`; a deixa calibra a tensão (`gritou`→sobe, `sussurrou`→desce); ações passam para a cena como sementes. |
| `orchestrator` (guard cross-track) | interrupção/sobreposição só valem DENTRO da mesma trilha — ninguém interrompe o narrador; cruzou de trilha → degrada p/ sequencial. |

Cadeia completa: `prosa .txt → Screenwriter → Director → Orquestrador → Renderer`.

## SFX + ambiência + ducking — SOM REAL (implementado)

Aqui o motor vira o que a visão pede: **história em texto → audiodrama com sons**. O
princípio é CITAR áudio real (biblioteca), não gerar tudo com IA — o Orquestrador e o
renderer não sabem se o som veio de um sample ou de síntese (mesmo truque do TTS).

| Peça | Papel |
|---|---|
| `models.SfxEvent` / `AmbienceEvent` | som PONTUAL (foley, duração real do sample, sequenciado) e CAMA ambiental (loopável, baixa, **localizada**: entra/sai de cena via `start_id`/`end_id`). Compartilham a interface de duck-typing do Orquestrador. |
| `sfx/base.py::SfxBackend` | contrato agnóstico (espelha `TTSBackend`): `render(event) → RenderedClip`. |
| `sfx/library.py::LibrarySfxBackend` | **áudio real** por tag (manifesto → arquivo), com fallback auditável; é o baseline de produção. |
| `sfx/procedural.py::ProceduralSfxBackend` | síntese determinística por tag (tiro, vento, passos_poca…) — o stand-in runnable, como o `FormantTTS` p/ voz. |
| `orchestrator` | posiciona SFX na sequência (fala pode reagir ao som) e ambiência como bed [0, total]; ganho por evento (não por tensão) p/ som. |
| `renderer._combine_tracks` (DUCKING) | a fala é a chave; ambiência/SFX/música afundam sob ela (`duck_db`) e voltam quando ela pára — via envelope de presença. É a mixagem profissional que impede a cacofonia. Ambiência é tiled p/ cobrir a cena. |

**Screenwriter refinado** (a descrição sonora vira SOM, não narração): cada frase é
classificada em diálogo / narração / **SFX** (som pontual) / **ambiência** (cenário
contínuo). "Passos numa poça d'água" vira efeito e o narrador NÃO o lê. O **narrador
é opcional** (`narrator=False` → modo radiodrama: só vozes + sons). `check_timeline`
só cobra sobreposição entre FALAS (som coexiste de propósito; o ducking resolve o nível).

**Diálogo reativo ao som**: como o SFX tem duração real medida, uma fala é ancorada
para reagir a ele (soldado grita → tiro → recruta reage) — a reação é resolvida no
render offline. Ver `examples/story_to_audio.py` (com `--sem-narrador`).

## Diretor de mix — `MixPolicy` (implementado)

O balanço entre as camadas num objeto só, no espírito do `TimingPolicy` (ritmo) e do
`ProsodyPolicy` (expressividade). `k_nar/mixpolicy.py::MixPolicy` centraliza os níveis
de bus por trilha (fala 0 dB de referência, narração −1, SFX −2, música −6…) e a
profundidade do ducking. São **dois níveis de ganho**: por EVENTO (o Director decide a
tensão da fala, a força do tiro) e por BUS (o mixador decide o balanço geral aqui). O
`renderer._combine_tracks` aplica o trim de bus e então o ducking — afinar o "som" do
audiodrama inteiro é ajustar um objeto. Um `MixPolicy` diferente = um estilo de mixagem.

## Biblioteca de som REAL (implementado)

O motor CITA áudio real em vez de gerar tudo. `k_nar/sfx/catalog.py` é a taxonomia
única (~55 sons: tag → categoria, ambiência, categoria ESC-50). `scripts/download_sfx.py`
baixa o [ESC-50](https://github.com/karoldvl/ESC-50) (2000 clipes, 50 categorias que
mapeiam quase 1:1 com áudio narrativo) **ciente de licença**: cada clipe tem a sua
(muitos CC0/CC-BY), o script prefere os mais livres e registra atribuição (`--free-only`
mantém só CC0/CC-BY). O `LibrarySfxBackend` trima/normaliza o SFX pontual e deixa a
ambiência inteira p/ loop; sons eletrônicos que o ESC-50 não tem (estática de rádio,
transformador, tom de discagem) são sintetizados no `ProceduralSfxBackend` (fallback).
Os léxicos do Screenwriter foram muito ampliados (PT/EN/ES) + diálogo por **travessão**
+ verbos de fala no **presente** + camas de ambiência capadas às 3 mais frequentes.

## Espacialização: distância + espaço acústico (implementado)

*De onde* o som vem, resolvido da prosa:

| Peça | Papel |
|---|---|
| `k_nar/proximity.py::ProximityPolicy` | matriz DISTÂNCIA → acústica: "ao longe" = −ganho + passa-baixa (o ar come os agudos) + mais central; "à queima-roupa" = +ganho, largo. Rótulo em `SfxEvent.distance`; o Screenwriter detecta (far/near words); o Orquestrador grava ganho/pan/`lowpass_hz` na EDL; o renderer aplica (`dsp.lowpass_1pole`). |
| `render/impulse.py` (presets) | ESPAÇO acústico: `galpao_vazio`, `catedral`, `caverna`, `quarto_pequeno`, `banheiro`, `tunel` (além dos antigos). O reverb convolutivo por cena já unia as vozes; agora o **lugar é detectado na prosa** ("galpão vazio" → eco na voz de todos) via `Screenwriter._detect_space`, ou fixado no front-matter `ambientacao`. |

Ver `examples/demo_espacializacao.md` (galpão + tiros perto/longe/horizonte).

## Ambiência localizada + balanço do mix (implementado)

Uma cama de ambiência não toca mais a cena inteira: ela **entra quando o elemento é
mencionado e sai na última menção + cauda** (com fade), então o "motor do jipe" só
soa a partir de quando ele entra em cena e some depois sem cortar do nada. O
Screenwriter ancora cada ambiência (`desde`/`ate` = ids de eventos); o Orquestrador
resolve em ms (`TimingPolicy.ambience_tail_ms`). Sem âncoras, cobre a cena (retrocompat).

Balanço: ambiências são normalizadas por **RMS** (`MixPolicy.ambience_rms`), não por
pico — sons densos (grilos, motor) não ficam altos demais; e o ducking é mais fundo
(`duck_db=-16`). Resultado medido: a ambiência fica ~-21 dB abaixo da narração
(desducada) e ~-24 dB sob a fala — um bed de fundo de verdade.

## "Set virtual" acústico por ZONAS — Nível 1 (implementado)

A ideia do usuário: o motor construir um **modelo da cena** (cômodos, quem está onde,
por onde o POV anda) e **derivar** a acústica dele — como áudio de jogo (o som bate na
parede e volta). A decisão de projeto foi a versão por **ZONAS**, não física de raios:
em estéreo, as reflexões colapsam e o ganho fica quase nulo perto do custo/fragilidade
de autorar geometria. O que o ouvido percebe é "em que cômodo estou" e "isso está no
meu cômodo ou atrás da parede" — e é isso que o modelo por zonas captura, barato e
reaproveitando o render que já existe.

| Peça | Papel |
|---|---|
| `k_nar/space/model.py::SceneModel` | Grafo de zonas (`Zone.space` = preset de reverb) + adjacência (portas) + `source_zone`/`listener_zone` por evento. `cue(id)` resolve um `SpatialCue`: reverb do cômodo do **ouvinte**, distância (mesma zona=perto; vizinha=longe; sem caminho=muito_longe via BFS) e **oclusão** (0/0.55/0.9). `is_trivial()` (≤1 zona) → no-op. Dado puro (stdlib), serializa p/ atravessar o Screenwriter. |
| `k_nar/space/policy.py::SpacePolicy` | Matriz OCLUSÃO → acústica: a parede é um passa-baixa físico. Interpola o corte (`open`→`wall_lowpass_hz`) e a atenuação (`wall_gain_db`) pela oclusão. |
| `orchestrator._apply_spatial` | Em modo espacial, grava na EDL o `space` (reverb do cômodo), a distância (via `ProximityPolicy`) e a oclusão (via `SpacePolicy`) — p/ diálogo e SFX; e p/ narração só em 1ª pessoa (`spatial_narration`). O narrador onisciente (3ª pessoa) fica **fora** do palco. |
| `renderer._reverb` | **Reverb POR-EVENTO**: convolve cada evento com o IR do seu cômodo e **estende a cauda** (o eco toca depois da fala). No modo espacial NÃO há reverb global — cada evento traz o seu, então o eco **segue o POV** pela casa. |
| `Screenwriter._zone_of` + `lexicons.zone_triggers` | Detecta cômodos na prosa ("cozinha"→quarto_pequeno, "sala"→sala_grande, "quintal"→seco) e monta o `SceneModel` (o POV "anda": adjacência na ordem da caminhada). Emite `espaco` no roteiro; o pipeline reconstrói. Só com 2+ cômodos. |

**A/B REAL** (`scripts/ab_spatial.py`, Piper + ESC-50): a voz do cômodo ao lado perde
~95% dos agudos e ~11 dB (oclusão); a cauda de reverb varia ~6× mais por cômodo (o
quintal aberto fica seco, o salão ecoa) vs. o modo flat (um reverb só). Sem regressão
de clipping/QA → **ligado por padrão** com 2+ cômodos. Ver `examples/casa_de_madeira.md`.

## Elenco de vozes por aparência + pessoa narrativa (implementado)

| Peça | Papel |
|---|---|
| `k_nar/casting.py` | Infere `Traits` (gênero/idade/timbre) de cada personagem dos **descritores** na prosa (uma frase com um só personagem credita seus traços — evita cross-atribuição). `voice_for` mapeia traço → `VoiceProfile` (pitch/ritmo): velho grave e lento, criança agudo e ágil. Gênero vem do texto, **nunca do nome** (não "misgenera"); sem descritor → voz neutra + jitter por nome p/ distinguir. |
| `k_nar/narrative/person.py` | `detect_person` conta pronomes de 1ª vs 3ª pessoa **na narração** (o diálogo sempre tem "eu"). 3ª = narrador onisciente **seco**; 1ª = a narração É o protagonista → mesma voz das falas dele (`protagonista`) e **dentro da cena** (`spatial_narration`, leva o reverb do cômodo). |
| Auto-atribuição em 1ª pessoa | `Screenwriter._attribution` marca falas sem nome com verbo de fala em 1ª pessoa ("gritei") ou pronome "eu" como `__EU__`; o pipeline casa `__EU__` com a voz da narração — o protagonista e o narrador têm a MESMA voz. |
| `pipeline._build_profiles` | Junta o elenco + o narrador (por pessoa) num `dict[personagem→VoiceProfile]` p/ o `MultiVoiceTTSBackend`. Front-matter `pessoa`/`protagonista`; CLI `--pessoa`/`--sem-espaco`. Templates: `examples/template_{primeira,terceira}_pessoa.md`. |

## Refinamentos de mixagem: qualidade de voz, material e fonte cross-room (implementado)

Feedback do usuário ao ouvir: a voz soava "160p" na 1ª pessoa, e os passos vinham
altos demais. Diagnóstico e correção:

| Problema | Causa | Correção |
|---|---|---|
| Voz "caixa/telefone" (abafada) | reverb por-evento a `wet=0.30` num cômodo pequeno pente a voz (reflexões cedo) — medido: HF cai ~78% | `renderer._wet_for(space)`: **wet por cômodo** (0.11 em quarto pequeno, até 0.26 em catedral). Cômodo pequeno fica seco → voz limpa; só grandes/vazios ganham cauda. Vale p/ o reverb global também. |
| Passos altos demais | `LibrarySfxBackend._condition` normalizava TODO SFX ao mesmo pico (0.9); foley percussivo tem pico alto mas deve sentar baixo | **Pico por categoria** (`_CATEGORY_PEAK`): foley 0.55, impacto 0.95. Passos sentam ~4 dB abaixo. |
| "Passos de bota em madeira ≠ chinelo em concreto" | não havia noção de material | `k_nar/material.py::MaterialPolicy`: material (superfície + calçado) → timbre (passa-baixa) + nível. `Screenwriter._material_of` detecta na prosa; o Orquestrador grava na EDL. Vale p/ qualquer foley. |
| "Uma voz vinda de outro cômodo" | a fonte era sempre o cômodo do POV | `Screenwriter._source_room` detecta "**da** cozinha, ela gritou" (marcador de origem + cômodo ≠ POV) → fonte noutra zona, POV parado → dispara a oclusão. Só vale p/ voz/SFX, não p/ a narração (o narrador não é relocado). |

## Atuação, mobília e voz de alta qualidade — Fase 8 (implementado)

| Peça | Papel |
|---|---|
| `k_nar/space/model.py::Zone.damping` + `PRESET_DAMPING` | Separa o TAMANHO do cômodo da sua ABSORÇÃO. Por padrão mobiliado → seco (escritório não vira caverna); vazio/nu → eco. `renderer._wet_for(space, damping)` reduz o wet por `1−damping`. O Screenwriter lê móveis vs. vazio (`lexicons.furnishing/emptiness/echo_words`) por zona e global. |
| `k_nar/emotion.py::EmotionPolicy` | Matriz EMOÇÃO → gesto vocal (arousal, ritmo, pitch, variância, ganho, pausas), irmã da `ProsodyPolicy`. `resolve(emo, intensidade)` escala o gesto. Composta em `ProsodyPolicy.resolve` (o emocional soma à tensão) e nas pausas do Orquestrador. |
| `k_nar/narrative/acting.py` | Inferência de emoção por regras: pontuação, léxico de emoção, verbo de fala, `SceneMood` (termômetro que sobe no suspense e decai), reação à linha anterior, e `Persona` (temperamento do personagem, dos descritores). O `RuleBasedDirector` mantém o mood/reação por história e grava emoção+intensidade no `voz`. |
| `k_nar/tts/xtts.py::XTTSBackend` | Voz XTTS-v2 (opt-in, `--voz xtts`) atrás do mesmo `TTSBackend`: locutor de estúdio por personagem (gênero, do casting) + `EmotionPolicy` (emoção→speed, pitch por reamostragem). Imports tardios (torch/coqui); o core segue stdlib. |
| `scripts/package_audio.py` | Entrega sob limite de tamanho: Opus (metade do MP3) e divisão em partes no silêncio. Zip/rar não serve (áudio já comprimido). |
| `story.strip_markdown` | Agora remove comentários HTML `<!-- -->` (são notas, não prosa — não podem ser lidos). |

## O que ainda NÃO existe (próximos passos)

1. **Música** com fonte dedicada (a trilha `musica` já é ducada e tem nível no
   `MixPolicy`; falta um `MusicEvent`/gerador — uma trilha via `LibrarySfxBackend` já roda).
2. **`LlamaDirector` para emoção fina** (o rótulo de emoção sairia de um LLM em vez de
   regras — o contrato é o mesmo; o baseline por regras já atua bem).
3. **Crossfade equal-power em `sobreposicao` longa**; **sincronia fina SFX↔verbo** via
   forced alignment sobre a narração; `NeuralSfxBackend`.

## Visão: motor de áudio narrativo completo (roadmap)

O alvo maior é o K-NAR deixar de ser um motor de *diálogo* e virar um motor de
*áudio narrativo*: dada uma história em prosa (cenas, ações, diálogos), gerar o
audiobook dramatizado inteiro — narração, vozes, foley (efeitos pontuais),
ambiência e (futuro) música. O insight é que a EDL já é a peça certa: um SFX é só
mais um evento na linha de tempo (início relativo, duração real, ganho, pan). As
fases 3–6 generalizam `SpeechEvent` numa união `Event`, tornam a Timeline
multitrack (buses de diálogo/foley/ambiência com ducking sidechain) e adicionam a
PASSAGEM 0 (Screenwriter: prosa → grafo de cenas). Ver `docs/ROADMAP.md`.
