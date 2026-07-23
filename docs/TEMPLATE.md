# Template de história — como escrever para o K-NAR

O K-NAR transforma uma **história em texto** num audiobook dramatizado (vozes que
**atuam**, efeitos, ambiência e espaço acústico). Um `.md`/`.txt` só com a sua prosa
já funciona — mas seguir estas convenções faz o motor interpretar **100%** do que
você quis. As regras abaixo foram **testadas** no próprio K-NAR: cada "✅ faça assim"
é um padrão que o parser acerta; cada "⚠️ evite" é um caso que ele erra.

## O arquivo

Front-matter opcional (entre `---`) no topo + a prosa embaixo:

```markdown
---
titulo: A Ponte de Comando
idioma: pt            # pt | en | es
narrador: sim         # sim / nao  (nao = radiodrama, só vozes + sons)
pessoa: terceira      # terceira | primeira | auto  (quem conta a história)
protagonista:         # em 1ª pessoa: o nome de quem narra
ambientacao: seco     # deixe 'seco' e deixe os cômodos definirem o espaço
---

A nave cortava o vazio. "Tem alguém aí?", perguntou a Comandante, tensa.
```

Defaults: `pt`, com narrador, `pessoa: auto`, ambiência `seco`. **Dois modelos
prontos:** `examples/template_terceira_pessoa.md` e `examples/template_primeira_pessoa.md`.

## Regra de ouro (as 3 que mais importam)

1. **Diálogo:** entre `"aspas"` **ou** travessão `— Fala —`, e **diga o nome de quem
   fala** na atribuição. ✅ `"Quem está aí?", perguntou Herman.` (ou `Herman perguntou`).
   ⚠️ **Evite atribuir só por pronome** — `perguntou ela` não vira um personagem
   nomeado (a voz sai genérica). Nomeie ao menos na primeira fala da troca.
2. **Um cômodo por frase** quando o personagem anda pela casa. ✅ `Entrou na cozinha.
   Fez café. Depois foi para a sala.` → o eco **segue** o POV (cozinha → sala).
   ⚠️ `Andou pelo corredor até a sala` (dois cômodos na mesma frase) conta só o
   **destino** (a sala) — o corredor não vira um cômodo à parte.
3. **Descreva a atuação:** o verbo de fala e as palavras de emoção **dirigem a voz**.
   ✅ `"CORRE!", gritou, apavorado.` → urgência/medo, alto e rápido.
   `"Calma…", murmurou, cansado.` → baixo, lento, contido.

## Como o K-NAR lê cada frase

| Você escreve | Vira |
|---|---|
| `"..."` ou `— ... —` | **DIÁLOGO** (com o locutor da atribuição) |
| `perguntou Ana`, `gritou o Capitão` | o **locutor** + a **emoção** da fala |
| `Um trovão ecoou.` (frase curta de som, sem nome) | **EFEITO** — o narrador **não** lê |
| `Ana ouviu a porta ranger.` (som + nome de pessoa) | **NARRAÇÃO + efeito** juntos |
| `Os grilos cantavam.` / `Chovia.` (cenário contínuo) | **AMBIÊNCIA** (cama de fundo) |
| o resto da prosa | **NARRAÇÃO** (se `narrador: sim`) |

## Atuação — faça os personagens *performar*

O K-NAR infere a **emoção de cada linha** e a atua (ritmo, tom, energia, tremor,
pausa). Dê os sinais:

- **Verbo de fala:** `gritou`/`berrou` (raiva), `sussurrou`/`murmurou` (suspense),
  `resmungou` (cansaço), `implorou` (súplica), `ordenou` (comando), `exclamou` (surpresa).
- **Palavras de emoção** perto da fala: *apavorado, furioso, triste, aliviado, feliz*.
- **Pontuação:** `!` = urgência/força; `...` = hesitação/suspense; `?` = pergunta;
  **MAIÚSCULAS** = grito.
- **Clima da cena:** o motor mantém um "termômetro" — uma sequência tensa
  (silêncio estranho, ameaça) **contamina** as falas seguintes com suspense, e uma
  fala carregada empurra a reação da próxima. Você não precisa marcar linha a linha:
  construa a tensão na prosa que o K-NAR acompanha.

## Vozes por personagem (elenco automático)

Descreva **idade, gênero e timbre** na primeira aparição — o K-NAR escolhe a voz:
✅ *"o **velho** Aurélio, de voz **rouca**"* → grave e lento; *"a **menina**"* → aguda
e ágil; *"o rapaz **nervoso**"* → mais agitado (temperamento também vira atuação). O
gênero vem dos **descritores**, nunca do nome. Sem descrição → voz neutra distinta.

## Espaço acústico (o "set virtual")

- **Cômodos:** nomeie os lugares (um por frase, ver regra 2). O eco **segue** o POV;
  a sala grande ecoa, o quintal é aberto e seco.
- **Mobiliado × vazio:** por padrão o cômodo é **mobiliado e seco** (nada de eco de
  caverna num escritório). Para ecoar, diga que está **vazio / em reforma / paredes
  nuas**; para reforçar o "seco", cite os móveis (*mesa, cadeira, estante, tapete*).
  Se você escrever que a voz *"ecoou"*, o eco é respeitado.
- **Voz de outro cômodo:** *"**da** cozinha, ela gritou"* (com **da/do**) → a voz soa
  abafada, atravessando a parede, enquanto o POV está noutro cômodo.
- **Distância de um som:** *"tiros **ao longe**"* (baixo e abafado) × *"à
  queima-roupa"* (alto e seco).
- **Material do passo/impacto:** *"passos de **bota** no **assoalho de madeira**"* ≠
  *"**chinelo** no **concreto**"* — muda timbre e volume.
- **Espaço fixo** (cena única): `ambientacao: galpao_vazio` (ou *catedral, caverna,
  túnel, banheiro*).

## Sons que o K-NAR reconhece

Não é lista fechada (o resto vira narração) — os mais comuns por idioma:

- **Efeitos:** tiro/disparo, explosão, porta que range, passos (+ `poça` → splash),
  trovão, vidro, batida, sirene, alarme, sino, buzina, teclado, latido, etc.
- **Ambiência:** floresta, grilos, chuva, vento, motor/nave, cidade, multidão, mar, fogo.

## Gerar o áudio

```bash
scripts/download_lang.sh pt            # vozes do idioma (uma vez): pt | en | es
python scripts/download_sfx.py         # biblioteca de efeitos reais (ESC-50, CC0)

python -m k_nar minha_historia.md                 # audiobook (usa sounds/ se existir)
python -m k_nar minha_historia.md --sem-narrador  # radiodrama (só vozes + sons)
python -m k_nar minha_historia.md --pessoa primeira
python -m k_nar minha_historia.md --voz xtts      # voz neural de ALTA qualidade (lenta)
```

`--voz xtts` usa o **XTTS-v2** (timbre muito melhor que o Piper padrão, porém lento —
segundos por frase; requer `coqui-tts` + `torch`). Para ouvir um teste rápido, use um
capítulo curto. Ou use a **interface web** (GitHub Pages) — veja o README.

## Checklist do documento perfeito

- [ ] Diálogo entre `"aspas"`/travessão, **com o nome** do locutor.
- [ ] Um **cômodo por frase** ao andar; diga se está **vazio** (senão é seco).
- [ ] **Verbos de fala + emoção** ricos (gritou/sussurrou/apavorado/cansado…).
- [ ] Cada personagem **descrito** (idade/gênero/timbre) na 1ª aparição.
- [ ] `pessoa:` e, em 1ª pessoa, `protagonista:` preenchidos.
- [ ] Sons pontuais em frases curtas; cenário contínuo para ambiência.
