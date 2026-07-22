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
[FUTURO: Environment DSP]
    Reverb convolutivo (IR por cena) + panning -> audio final coeso.
```

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

## O que ainda NÃO existe (próximos passos)

1. **Crossfade equal-power em `sobreposicao` longa** (hoje o equal-power cobre a
   costura de interrupção; na fala simultânea prolongada as vozes dependem do limiter).
2. Calibrar mais o `LlamaDirector`: o few-shot quebrou a saturação, mas o 1.5B ainda
   subusa "baixa". Mais exemplos ou um modelo maior sharpeariam a escala.
3. As **fases narrativas** (3–6): união `Event`, Timeline multitrack, Screenwriter
   (PASSAGEM 0), SFX/foley + ambiência + ducking. Ver `docs/ROADMAP.md`.

## Visão: motor de áudio narrativo completo (roadmap)

O alvo maior é o K-NAR deixar de ser um motor de *diálogo* e virar um motor de
*áudio narrativo*: dada uma história em prosa (cenas, ações, diálogos), gerar o
audiobook dramatizado inteiro — narração, vozes, foley (efeitos pontuais),
ambiência e (futuro) música. O insight é que a EDL já é a peça certa: um SFX é só
mais um evento na linha de tempo (início relativo, duração real, ganho, pan). As
fases 3–6 generalizam `SpeechEvent` numa união `Event`, tornam a Timeline
multitrack (buses de diálogo/foley/ambiência com ducking sidechain) e adicionam a
PASSAGEM 0 (Screenwriter: prosa → grafo de cenas). Ver `docs/ROADMAP.md`.
