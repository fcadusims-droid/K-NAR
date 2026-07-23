# K-NAR

Motor de **Performance Dramática** para áudio drama autônomo. Em vez de gerar
arquivos de fala isolados e colá-los (ritmo mecânico, vozes num vácuo), o K-NAR
funciona como uma engine orientada a **linha de tempo**: o texto vira metadados
de tempo e performance, e o áudio é renderizado depois num espaço acústico coeso.

## A ideia em uma frase

> O LLM é o **Diretor de Palco** (gera *intenção relativa*: tensão, agressividade,
> pausas). O código é o **contra-regra** (traduz intenção + duração real do áudio
> em milissegundos). O motor de áudio é o **palco** (reverb e panning). Ninguém faz
> o trabalho do outro.

## O Orquestrador de Duas Passagens

Resolve a dependência circular "preciso do tempo pra montar a cena, mas o tempo só
existe depois de sintetizar":

```
PASSAGEM 1  LLM   -> texto + metadados RELATIVOS  (nunca segundos)
PASSAGEM 2  TTS   -> sintetiza "seco" e MEDE a duracao real
PASSAGEM 3  Code  -> cruza relativo x real -> Timeline (dados puros)
```

Detalhes em [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Estado atual

**Core (stdlib puro, sem dependências):**

- `Orquestrador` — as passagens 2 e 3.
- `TimingPolicy` — a matriz relativo→ms, com guardas de inteligibilidade e agora
  também os **envelopes de atenuação** que a EDL carrega (fades anti-clique).
- `TTSBackend` — contrato agnóstico; `MockTTSBackend` para testar sem motor de voz.
- `Timeline` — a Edit Decision List que o DSP consome.
- `schema.validate_scene` — validação **estrita** do JSON do LLM (recusa fallback silencioso).

**Camada Director (`k_nar/director/`) — PASSAGEM 1:**

- `RuleBasedDirector` — roteiro cru → metadados relativos por heurística (sem modelo).
- `LlamaDirector` — o mesmo, com um LLM local pequeno (Qwen2.5-1.5B GGUF, CPU).

**Expressividade (`k_nar/prosody.py`):**

- `ProsodyPolicy` — a matriz que traduz tensão em manipuladores acústicos reais
  (rate, pitch, variância, ganho). Fonte única lida pelo TTS e pelo Orquestrador,
  para a emoção mover a onda, o corte e o mix juntos (o Piper é inerte à semântica).

**TTS (`k_nar/tts/`):**

- `PiperTTSBackend` — voz **neural real** (Piper/onnx, CPU): fonemas, plosivas,
  respiração. Aplica a `ProsodyPolicy` (rate via `length_scale`, pitch por reamostragem).
- `CachingTTS` — cache em disco por conteúdo: iterar não re-sintetiza (0.40s → 0.01s).
- `synthesize_all` — passagem 2 em paralelo (pool de threads).
- `FormantTTSBackend` / `MockTTSBackend` — voz sintética / só-duração, para testes.

**Camada DSP (`k_nar/render/`, requer `numpy` + `pedalboard`):**

- `TrimmedTTS` — remove o padding de silêncio do TTS antes de medir a duração.
- `TimelineRenderer` — materializa a EDL em áudio estéreo: fades anti-clique, snap do
  corte ao vale de energia, **crossfade equal-power** na interrupção, panning e **bus
  de reverb convolutivo** único por cena. Modos `naive`/`dry`/`full` para A/B.

**Forced alignment (`k_nar/align.py`):**

- `Alignment` — fronteiras fonema→amostra do próprio Piper/VITS (`include_alignments`,
  requer `onnx`). O corte de interrupção ancora numa fronteira de palavra/fonema REAL
  (decidido no Orquestrador, dado puro) e o renderer só refina o instante acústico numa
  janela estreita. Snap de energia vira fallback para backends sem fonemas.

**Voz por personagem + QA (`k_nar/tts/multivoice.py`, `k_nar/qa.py`):**

- `MultiVoiceTTSBackend` — `VoiceProfile` por personagem (modelo Piper próprio,
  `speaker_id`, pitch/ritmo). Roteia atrás do mesmo `TTSBackend`; o Orquestrador não muda.
- `check_timeline`/`check_mix` — QA automatizado: overlaps que engolem, cortes
  agressivos, clipping. Rodam no CI a cada push/PR.

**Narração e áudio narrativo (`k_nar/models.py`, `k_nar/narrative/`):**

- `Track` + `NarrationEvent` — a linha de tempo vira multitrack (diálogo/narração/…);
  o renderer mixa por trilha (base do ducking).
- `RuleBasedScreenwriter` (PASSAGEM 0) — prosa → narração + diálogo (com locutor) +
  **SFX** (som pontual) + **ambiência** (cenário). Descrição sonora vira SOM, não
  narração; o **narrador é opcional** (modo radiodrama). Cadeia em `examples/story_to_audio.py`.

**Som: SFX + ambiência + ducking (`k_nar/sfx/`, `render/renderer.py`):**

- `SfxBackend` (espelha `TTSBackend`): `LibrarySfxBackend` (samples **reais** por tag,
  baseline de produção) e `ProceduralSfxBackend` (síntese, stand-in runnable).
- **Biblioteca real**: `scripts/download_sfx.py` baixa o ESC-50 (50 categorias de som)
  **ciente de licença** (prefere CC0/CC-BY). Catálogo de ~55 sons em `k_nar/sfx/catalog.py`.
- `SfxEvent` / `AmbienceEvent` — som pontual (foley, ancora a fala p/ reagir) e cama.
- **Ducking sidechain** no `_combine_tracks`: ambiência/SFX afundam sob a fala e voltam
  quando ela pára — a mixagem que impede a cacofonia. O `duck_db` controla a profundidade.

**Espacialização (`k_nar/proximity.py`, `k_nar/space/`, `render/impulse.py`):**

- **Distância** (`ProximityPolicy`): "tiros ao longe" = baixo, abafado (passa-baixa) e
  central; "à queima-roupa" = alto e largo — detectado da prosa.
- **Espaço** (presets de IR): "galpão vazio / catedral / caverna" → a voz ganha o eco do
  lugar (reverb convolutivo por cena), detectado da prosa ou fixo no front-matter.
- **"Set virtual" de zonas** (`SceneModel`, Nível 1): quando a prosa passa por **2+
  cômodos**, o K-NAR monta um **mapa da casa** (cômodos + portas). O **reverb segue o
  POV** de cômodo em cômodo, e uma voz do **cômodo ao lado** soa **abafada** (oclusão:
  a parede come os agudos e derruba o nível). A acústica é **derivada do modelo**, não
  de rótulos à mão. A/B real: `scripts/ab_spatial.py` (oclusão −95% de agudos entre
  cômodos; cauda de reverb varia 6× mais por cômodo, sem regressão de mix).

**Material do foley (`k_nar/material.py`):**

- Passo de **bota em madeira** ≠ **chinelo em concreto**: o K-NAR lê o material
  (superfície + calçado) na prosa e ajusta **timbre** (materiais macios abafam) e
  **nível** (bota soca, chinelo é discreto). Vale p/ qualquer foley, não só passos.
- **Nível por categoria**: foley (passos) senta mais baixo que um impacto (tiro) —
  não vão mais todos ao mesmo volume.

**Elenco de vozes por aparência (`k_nar/casting.py`):**

- O K-NAR **infere idade/gênero/timbre** de cada personagem dos **descritores** na prosa
  ("o velho de voz rouca" → grave e lento; "a menina" → agudo e ágil) e escolhe a voz
  (pitch/ritmo sobre o modelo base). Sem descritor → voz neutra; o gênero vem do texto,
  nunca de adivinhar pelo nome.

**Pessoa narrativa (`k_nar/narrative/person.py`):**

- **3ª pessoa** — narrador onisciente, voz própria e **seca** (fora da cena). **1ª pessoa**
  — a narração É o protagonista: **mesma voz** das falas dele e **dentro da cena** (leva o
  eco do cômodo). Detectado da narração (`pessoa: auto`) ou fixo no front-matter.

**Atuação — os personagens *performam* (`k_nar/emotion.py`, `k_nar/narrative/acting.py`):**

- O K-NAR **infere a emoção de cada linha** (pontuação, palavras de emoção, o verbo de
  fala, o **clima da cena** que sobe no suspense, e a **reação** à linha anterior) e a
  atua via `EmotionPolicy` — ritmo, tom, tremor, ganho e **pausas**. Medo = agudo/rápido/
  trêmulo; raiva = grave/forte/alto; tristeza = lento/baixo. Cada personagem tem um
  **temperamento** (o veterano calmo × o novato nervoso) que enviesa a atuação.

**Cômodo mobiliado × vazio (`k_nar/space/`):**

- Um cômodo **mobiliado e em uso é seco** (a mobília absorve) — nada de "eco de caverna"
  num escritório. Só um espaço **vazio/nu/em reforma** ecoa. O K-NAR lê os móveis e as
  pistas de vazio na prosa e ajusta a absorção (`Zone.damping`).

**Voz de ALTA qualidade — XTTS (`k_nar/tts/xtts.py`, opt-in):**

- `--voz xtts` troca o Piper pelo **XTTS-v2** (timbre muito mais natural, prosódia viva),
  com voz por personagem via locutor de estúdio + a mesma `EmotionPolicy`. É **lento**
  (segundos/frase; requer `coqui-tts` + `torch`) — opt-in. O Piper segue o padrão rápido.

**Entrega sob limite de tamanho (`scripts/package_audio.py`):**

- Audiobook longo em qualidade máxima → **Opus** (metade do tamanho do MP3 na mesma
  qualidade); se ainda passar do limite, **divide em partes** (cortando no silêncio),
  cada uma sob o teto. Zip/rar não serve (áudio já é comprimido).

Roadmap em [`docs/ROADMAP.md`](docs/ROADMAP.md); detalhes das fases em
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Usar (história → audiobook)

Escreva a história num `.md`/`.txt` (formato em [`docs/TEMPLATE.md`](docs/TEMPLATE.md)) e rode a CLI:

```bash
scripts/setup.sh                     # deps (numpy + pedalboard + piper + onnx) + voz PT
scripts/download_lang.sh en          # (opcional) voz de outro idioma: en | es

python -m k_nar examples/historia_template.md          # -> examples/historia_template.wav
python -m k_nar examples/casa_de_madeira.md            # anda por 4 cômodos (espacial)
python -m k_nar minha_historia.md -o audiobook.wav
python -m k_nar minha_historia.md --sem-narrador       # modo radiodrama (só vozes + sons)
python -m k_nar minha_historia.md --pessoa primeira    # narração na voz do protagonista
python -m k_nar minha_historia.md --sem-espaco         # desliga o reverb por cômodo
python -m k_nar minha_historia.md --idioma en          # pt | en | es (sobrescreve o front-matter)
python -m k_nar minha_historia.md --sons sounds/       # samples reais (sounds/manifest.json)
```

O front-matter define título, idioma, narrador (sim/não), **pessoa** (1ª/3ª) e
ambientação; nada é obrigatório (um `.md` só com prosa funciona). Modelos prontos:
`examples/template_terceira_pessoa.md` e `examples/template_primeira_pessoa.md`.
Multi-idioma: **pt / en / es**.

## Interface web (GitHub Pages + Actions)

Usuários geram audiobooks **sem instalar nada**:

1. Abrem a **página** (GitHub Pages: `docs/index.html`) — escrevem a história, escolhem
   idioma e narrador on/off, e clicam em *Gerar*.
2. O botão abre um **issue já preenchido** (formulário `🎧 Gerar audiobook`).
3. A **GitHub Action** (`.github/workflows/audiobook.yml`) renderiza a história e
   comenta no issue o link para baixar o `audiobook.wav`.

Para ativar no seu fork (uma vez): **Settings → Actions** (habilitar workflows) e
**Settings → Pages → Source: `main` / `/docs`**. Ajuste `REPO` no topo do
`<script>` em `docs/index.html` se o fork tiver outro nome. Também dá para rodar o
workflow manualmente em **Actions → audiobook → Run workflow**.

## Rodar os exemplos

```bash
# core: imprime a linha de tempo (sem dependencias)
python -m examples.run_mvp

# instalar deps de DSP (e opcionalmente o LLM local)
scripts/setup.sh            # numpy + pedalboard
scripts/setup.sh --llm      # + llama-cpp-python + baixa o modelo (~1.1GB)

# gerar AUDIO da cena (naive / dry / full) em build_audio/
python -m examples.render_scene

# pipeline COMPLETO: roteiro cru -> Director -> Orquestrador -> audio
python -m examples.direct_and_render                 # Director por regras
python -m examples.direct_and_render examples/roteiro_exemplo.json --llm   # Director LLM

# pipeline NEURAL: voz Piper real + cache + sintese paralela + forced alignment
python -m examples.render_neural                 # Director por regras
python -m examples.render_neural roteiro.json --llm   # Director LLM (few-shot)

# voz DISTINTA por personagem (faber+jeff) + relatorio de QA acustico
scripts/download_piper.sh jeff                    # segunda voz real
python -m examples.multivoice_qa

# HISTORIA em prosa -> AUDIODRAMA (vozes + SFX + ambiencia + ducking)
python -m examples.story_to_audio                 # usa examples/historia_sonora.txt
python -m examples.story_to_audio minha_historia.txt
python -m examples.story_to_audio --sem-narrador  # modo radiodrama (so vozes + sons)

# cena narrada (narrador + personagens em trilhas separadas)
python -m examples.narrated_scene

# provas: trim + crossfade | expressividade (mesma frase em 4 tensoes)
python -m examples.proof_dsp
python -m examples.proof_prosody

# testes (core + DSP + Director; os de DSP pulam se numpy faltar)
python -m unittest discover -s tests -v
```

## Contrato JSON (saída do LLM — PASSAGEM 1)

```json
{
  "cena_id": "ponte_comando_01",
  "ambientacao": "cockpit_metalico_eco",
  "eventos": [
    {
      "id": "fala_1",
      "personagem": "Alien A",
      "texto": "O nucleo nao deve ser ativado.",
      "voz":     { "tensao": "alta", "velocidade": 0.85, "tom": -0.1 },
      "entrada": { "tipo": "sequencial" },
      "saida":   { "pausa": "curta" },
      "palco":   { "estereo": -30 }
    },
    {
      "id": "fala_2",
      "personagem": "Alien B",
      "texto": "Voce teme o inevitavel!",
      "voz":     { "tensao": "extrema", "velocidade": 1.1 },
      "entrada": { "tipo": "interrupcao", "agressividade": 0.25 },
      "saida":   { "pausa": "media" },
      "palco":   { "estereo": 20 }
    }
  ]
}
```
