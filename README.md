# K-NAR

**Narrador privado para conteúdo de redes sociais.** Você manda o **roteiro** de um
vídeo/post e o K-NAR devolve **um arquivo de áudio narrado** — voz neural natural,
fiel ao texto, na ordem, sem inventar som, trilha ou "atuação". A voz roda **local**
(XTTS-v2), então nada do seu roteiro precisa sair da sua máquina.

## A ideia em uma frase

> Roteiro em texto → **um** narrador lê como está → um arquivo de áudio pronto pro
> seu editor de vídeo. Fidelidade ao roteiro, não interpretação.

## Como funciona

Três passos (`k_nar/narrator.py`):

```
1. SEGMENTAR   o texto vira frases (respiro curto) agrupadas em parágrafos (respiro maior)
2. SINTETIZAR  cada frase passa pelo motor de voz (XTTS), com trim de silêncio + cache
3. MONTAR      concatena tudo com as pausas, normaliza e escreve um WAV (ou .ogg/.mp3)
```

O motor de voz é **agnóstico** (um `TTSBackend`): XTTS-v2 local por padrão, ou um
stand-in sintético (`formante`) para rascunho/testes sem baixar torch.

## Instalar e usar

```bash
scripts/setup.sh --xtts        # torch/torchaudio (CPU) + coqui-tts (combo validado); modelo ~1.8GB no 1º uso

python -m k_nar roteiro.txt                          # -> roteiro.wav
python -m k_nar roteiro.txt -o narracao.wav
python -m k_nar roteiro.txt --velocidade 1.1         # acelera a leitura
python -m k_nar roteiro.txt --locutor "Ana Florence" # troca o locutor de estúdio
python -m k_nar roteiro.txt --voz-ref minha_voz.wav  # CLONA a sua voz de um sample
python -m k_nar roteiro.txt --idioma en              # pt | en | es
python -m k_nar roteiro.txt --formato opus           # entrega comprimida (.ogg), sob limite
python -m k_nar roteiro.txt --motor formante         # rascunho offline (sem torch)
```

O roteiro é um `.txt`/`.md`: **só o texto a narrar**, um parágrafo por bloco.
Cabeçalhos de Markdown (`# ...`) e comentários (`<!-- ... -->`) são ignorados — use-os
para se organizar sem que entrem no áudio. Front-matter opcional define título, idioma,
voz e ritmo. Formato completo em [`docs/TEMPLATE.md`](docs/TEMPLATE.md); exemplo em
[`examples/roteiro_yt_exemplo.txt`](examples/roteiro_yt_exemplo.txt).

## A voz

Duas formas de escolher (XTTS-v2, local e privado):

- **Locutor de estúdio** — o padrão é uma **voz masculina** grave e calma (`Damien Black`);
  troque com `--locutor "Nome"` (ou no front-matter). O XTTS traz ~58 timbres masc./fem.
  (ex.: `Dionisio Schuyler`, `Aaron Dreschner`, `Ana Florence`).
- **A sua própria voz** — `--voz-ref minha_voz.wav` clona o timbre de um sample curto
  (6–20s). É o "narrador privado" de verdade: sua voz, sem nada sair da máquina.
  Requer **FFmpeg** instalado (o torchaudio carrega o wav de referência por ele):
  `apt-get install -y ffmpeg` (Linux) ou `brew install ffmpeg` (macOS). A narração com
  locutor de estúdio (sem `--voz-ref`) não precisa disso.

A leitura é **neutra por design** — o narrador não "atua". A única alavanca de
performance é `--velocidade`.

## Site local (recomendado) — enviar `.md` e baixar o áudio

Um site que roda **na sua máquina** (100% local, sem API, **sem limite de tamanho** de
roteiro): você arrasta um `.md`/`.txt` e baixa o `.wav`.

```bash
scripts/setup.sh --xtts        # uma vez
python -m k_nar.web            # abre em http://127.0.0.1:8000
```

Simples e direto: escolha o arquivo, ajuste velocidade/idioma/locutor e clique em
*Gerar narração*. O roteiro vai no corpo do POST (não numa URL), então **não há o limite
de tamanho** do fluxo por issue. É o jeito certo para roteiros longos.

## GitHub Pages + Actions (zero-install, com limite)

A página estática ([`docs/index.html`](docs/index.html) via GitHub Pages) abre um
**issue já preenchido**; a **Action** ([`.github/workflows/narrar.yml`](.github/workflows/narrar.yml))
narra e comenta o link do `narracao.wav`. Não exige instalar nada, **mas**: GitHub Pages
é estático (não roda o XTTS), então a síntese acontece na Action, e o roteiro trafega
pelo issue — que tem **limite de tamanho**. Para roteiros grandes, use o site local acima.

Ativar no fork (uma vez): **Settings → Actions** (habilitar workflows) e **Settings →
Pages → Source: `main` / `/docs`**. Ajuste `REPO` no topo do `<script>` em `docs/index.html`.

## Arquitetura (enxuta)

| Módulo | Papel |
|---|---|
| `k_nar/script.py` | Lê o roteiro: front-matter (`chave: valor`, stdlib) + limpeza de Markdown. |
| `k_nar/narrator.py` | Os 3 passos: `segment_script` (por parágrafo), `assemble`, `narrate` + o factory de voz (`build_backend`). |
| `k_nar/web.py` | Site LOCAL: sobe um servidor (`python -m k_nar.web`) p/ enviar `.md` e baixar o `.wav`, sem limite de tamanho. |
| `k_nar/models.py` | `SpeechEvent`/`VoiceParams` — o contrato mínimo que o motor de voz consome. |
| `k_nar/tts/base.py` | `TTSBackend` (Protocol agnóstico) + `RenderedClip` (com a duração real medida). |
| `k_nar/tts/xtts.py` | `XTTSBackend`: voz neural XTTS-v2 (locutor de estúdio ou clonagem). Imports pesados são tardios. |
| `k_nar/tts/cache.py` | `CachingTTS`: cache em disco por conteúdo — reeditar uma frase não re-sintetiza o resto. |
| `k_nar/tts/batch.py` | `synthesize_all`: sintetiza as frases (serial por padrão — o XTTS/torch não é thread-safe e já usa todos os núcleos por chamada; `workers>1` fica para backends que liberam o GIL). |
| `k_nar/render/trim.py` | `TrimmedTTS`: remove o padding de silêncio antes de medir a duração. |
| `k_nar/render/voice.py` | `FormantTTSBackend`: voz sintética de rascunho (offline, sem torch). |
| `k_nar/prosody.py` / `emotion.py` | Matrizes de prosódia/emoção, instanciadas **neutras** no narrador (existem para uma futura leitura expressiva). |
| `scripts/package_audio.py` | Entrega sob limite de tamanho: Opus/MP3, dividindo no silêncio se preciso. |

A segmentação e a leitura do roteiro são **stdlib puro**; `numpy` só é exigida na
montagem do áudio, e o XTTS (torch/coqui) é carregado sob demanda.

## Limitações honestas

- **XTTS em CPU é lento** e baixa ~1.8GB no 1º uso. Medido aqui (CPU, sem GPU): a carga
  do modelo na RAM leva ~2 min **por processo** (custo único, amortizado num roteiro
  longo) e a síntese roda em segundos por frase. Para volume, use uma máquina com GPU.
  O cache (`.knar_cache/`) evita re-sintetizar o que não mudou entre execuções.
- **`--motor formante` é rascunho**, não voz de verdade: serve para conferir ritmo,
  pausas e segmentação sem baixar nada. Não use no produto final.
- A **qualidade final é a do XTTS-v2**. É bom, mas não é ElevenLabs; avalie com o seu
  ouvido antes de publicar.

## Testes

```bash
pip install numpy
python -m unittest discover -s tests -v
```

Os testes usam o motor `formante` (offline) — não baixam torch/XTTS. A CI roda a suíte
a cada push/PR.
