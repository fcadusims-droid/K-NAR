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

1. Backend **XTTS real** implementando `TTSBackend` (voz local com palavras).
   Aí `snap_to_valley` pode evoluir para forced alignment de verdade sobre os fonemas.
2. **Crossfade equal-power** explícito em `sobreposicao` (hoje as vozes coexistem
   somadas; falta a curva de igual potência na zona de sobreposição).
3. QA acústico automatizado (detectar clipping, overlaps que engolem palavras) —
   `Timeline.overlaps()` é a semente.
4. O **prompt/contrato do LLM** que produz o JSON da PASSAGEM 1 (validado por `schema`).
