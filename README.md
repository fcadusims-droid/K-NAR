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
scripts/setup.sh --xtts        # numpy + coqui-tts + torch (o modelo ~1.8GB baixa no 1º uso)

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

- **Locutor de estúdio** — `--locutor "Dionisio Schuyler"` (ou no front-matter). O XTTS
  traz vários timbres masc./fem.
- **A sua própria voz** — `--voz-ref minha_voz.wav` clona o timbre de um sample curto
  (6–20s). É o "narrador privado" de verdade: sua voz, sem nada sair da máquina.

A leitura é **neutra por design** — o narrador não "atua". A única alavanca de
performance é `--velocidade`.

## Interface web (GitHub Pages + Actions)

Gerar sem instalar nada:

1. Abra a **página** ([`docs/index.html`](docs/index.html) via GitHub Pages) — cole o
   roteiro, escolha o idioma e clique em *Gerar narração*.
2. O botão abre um **issue já preenchido** (formulário `🎙️ Gerar narração`).
3. A **GitHub Action** ([`.github/workflows/narrar.yml`](.github/workflows/narrar.yml))
   narra o roteiro e comenta no issue o link para baixar o `narracao.wav`.

Para ativar no seu fork (uma vez): **Settings → Actions** (habilitar workflows) e
**Settings → Pages → Source: `main` / `/docs`**. Ajuste `REPO` no topo do `<script>`
em `docs/index.html` se o fork tiver outro nome.

## Arquitetura (enxuta)

| Módulo | Papel |
|---|---|
| `k_nar/script.py` | Lê o roteiro: front-matter (`chave: valor`, stdlib) + limpeza de Markdown. |
| `k_nar/narrator.py` | Os 3 passos: `segment_script`, `assemble`, `narrate` + o factory de voz (`build_backend`). |
| `k_nar/models.py` | `SpeechEvent`/`VoiceParams` — o contrato mínimo que o motor de voz consome. |
| `k_nar/tts/base.py` | `TTSBackend` (Protocol agnóstico) + `RenderedClip` (com a duração real medida). |
| `k_nar/tts/xtts.py` | `XTTSBackend`: voz neural XTTS-v2 (locutor de estúdio ou clonagem). Imports pesados são tardios. |
| `k_nar/tts/cache.py` | `CachingTTS`: cache em disco por conteúdo — reeditar uma frase não re-sintetiza o resto. |
| `k_nar/tts/batch.py` | `synthesize_all`: síntese em paralelo (pool de threads). |
| `k_nar/render/trim.py` | `TrimmedTTS`: remove o padding de silêncio antes de medir a duração. |
| `k_nar/render/voice.py` | `FormantTTSBackend`: voz sintética de rascunho (offline, sem torch). |
| `k_nar/prosody.py` / `emotion.py` | Matrizes de prosódia/emoção, instanciadas **neutras** no narrador (existem para uma futura leitura expressiva). |
| `scripts/package_audio.py` | Entrega sob limite de tamanho: Opus/MP3, dividindo no silêncio se preciso. |

A segmentação e a leitura do roteiro são **stdlib puro**; `numpy` só é exigida na
montagem do áudio, e o XTTS (torch/coqui) é carregado sob demanda.

## Limitações honestas

- **XTTS em CPU é lento** (segundos por frase) e baixa ~1.8GB no 1º uso. Para roteiros
  longos, conte tempo — ou rode numa máquina com GPU. O cache evita re-sintetizar o que
  não mudou.
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
