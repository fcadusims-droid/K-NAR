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

## O que ainda NÃO existe (próximos passos)

1. Backend **XTTS real** implementando `TTSBackend` (voz local com palavras). O
   encaixe já está pronto: `TrimmedTTS` neutraliza o padding e o `TTSBackend` é o
   contrato. Aí `snap_to_valley` evolui para forced alignment sobre os fonemas reais.
2. **Crossfade equal-power em `sobreposicao` longa** (hoje o equal-power cobre a
   costura de interrupção; na fala simultânea prolongada as vozes somam e dependem
   do limiter — falta a curva dedicada de coexistência).
3. QA acústico automatizado (detectar clipping, overlaps que engolem palavras) —
   `Timeline.overlaps()` é a semente.
4. Afinar o prompt do `LlamaDirector` (o modelo pequeno tende a saturar tudo em
   "alta"); poucos exemplos few-shot devem calibrar a escala de tensão.
