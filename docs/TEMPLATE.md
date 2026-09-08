# Template de roteiro — como escrever para o K-NAR

O K-NAR é um **narrador**: você manda o **roteiro** de um vídeo/post e ele devolve o
áudio narrado, **fiel ao texto** — na ordem, sem inventar som, trilha ou "atuação". Um
`.txt`/`.md` só com o texto já funciona; o front-matter abaixo é opcional e só ajusta
voz e ritmo.

## O arquivo

Front-matter opcional (entre `---`) no topo + o texto a narrar embaixo:

```markdown
---
titulo: Como o algoritmo do YouTube funciona
idioma: pt                     # pt | en | es
locutor: Dionisio Schuyler     # locutor de estúdio do XTTS (opcional)
voz_ref: minha_voz.wav         # OU clona a SUA voz de um sample (opcional)
velocidade: 1.0                # 1.0 neutro; 1.1 acelera; 0.9 desacelera
pausa_frase: 350               # ms de respiro entre frases
pausa_paragrafo: 750           # ms de respiro entre parágrafos
---

Todo mundo acha que sabe como o algoritmo funciona. Quase ninguém sabe.

Neste vídeo eu vou te mostrar os três sinais que realmente importam.
```

Defaults: `pt`, locutor padrão, velocidade `1.0`. Nada é obrigatório.

## Como o narrador lê o roteiro

- **Um parágrafo por bloco** (separado por uma linha em branco). Entre parágrafos o
  narrador dá um respiro maior (`pausa_paragrafo`); entre as frases de um parágrafo,
  um respiro curto (`pausa_frase`).
- **Frases** quebram na pontuação (`. ! ? …`). Abreviações comuns (`Sr.`, `Dr.`,
  `etc.`) **não** cortam a frase.
- **É lido como está.** O narrador não interpreta personagens nem emoção — a voz sai
  neutra e fiel. Se quiser mais rápido/devagar, use `velocidade`.

### O que é ignorado (não é narrado)

- **Cabeçalhos de Markdown** (`# Seção`, `## Parte 2`) — são rótulos de estrutura.
- **Comentários HTML** (`<!-- nota pra mim -->`) e **blocos de código** (``` ``` ```).
- Sintaxe de **ênfase/links/listas** é limpa, mas o **texto** dela é lido.

> Dica: use os cabeçalhos para se organizar (Introdução, Desenvolvimento, CTA) sem
> medo — eles não entram no áudio.

## A voz

Duas formas de escolher a voz (XTTS-v2, local):

1. **Locutor de estúdio** — um nome em `locutor:`. Alguns: `Dionisio Schuyler`,
   `Craig Gutsy`, `Baldur Sanjin` (masc.); `Daisy Studious`, `Ana Florence`,
   `Sofia Hellen` (fem.).
2. **A sua própria voz** — aponte `voz_ref:` para um `.wav` curto (uns 6–20s) da sua
   voz. O K-NAR clona o timbre. É o "narrador privado" de verdade: nada sai da máquina.

`voz_ref` tem prioridade sobre `locutor` quando os dois vêm.

## Gerar o áudio

```bash
scripts/setup.sh --xtts                 # numpy + coqui-tts + torch (uma vez)

python -m k_nar roteiro.txt                          # -> roteiro.wav
python -m k_nar roteiro.txt -o narracao.wav
python -m k_nar roteiro.txt --velocidade 1.1         # acelera a leitura
python -m k_nar roteiro.txt --locutor "Ana Florence" # troca o locutor
python -m k_nar roteiro.txt --voz-ref minha_voz.wav  # clona a SUA voz
python -m k_nar roteiro.txt --idioma en              # pt | en | es
python -m k_nar roteiro.txt --formato opus           # entrega comprimida (.ogg)
python -m k_nar roteiro.txt --motor formante         # rascunho offline (sem torch)
```

O **XTTS é lento em CPU** (segundos por frase) e baixa o modelo (~1.8GB) no 1º uso.
Para um teste rápido do ritmo/segmentação sem baixar nada, use `--motor formante`
(voz sintética de rascunho). Ou use a **interface web** (GitHub Pages) — veja o README.

## Checklist do roteiro

- [ ] Um **parágrafo por bloco** (linha em branco entre eles).
- [ ] Cabeçalhos/anotações que **não** devem ser lidos ficam como `#`/`<!-- -->`.
- [ ] Escolheu a voz (`locutor:` ou `voz_ref:`) e a `velocidade`, se quiser mudar.
