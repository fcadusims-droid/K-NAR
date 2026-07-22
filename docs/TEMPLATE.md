# Template de história — como escrever para o K-NAR

O K-NAR transforma uma **história em texto** num audiobook dramatizado (vozes,
efeitos e ambiência). Você **não precisa** de um formato rígido: um `.md` ou `.txt`
só com a sua prosa já funciona. Mas seguir estas convenções melhora o resultado.

## O arquivo

Um `.md` (ou `.txt`) com um **front-matter** opcional no topo (entre `---`) e a
história em prosa embaixo:

```markdown
---
titulo: A Ponte de Comando
idioma: pt            # pt | en | es
narrador: sim         # sim / nao  (com ou sem narrador)
ambientacao: cockpit_metalico_eco
---

A nave cortava o vazio, e o zumbido dos motores enchia a ponte.
Uma porta blindada rangeu. "Tem alguém aí?", perguntou a Comandante, tensa.
Ninguém respondeu. Então um tiro disparou nas sombras.
"Todos em posição!", ela gritou.
```

Todos os campos do front-matter são opcionais (defaults: `pt`, com narrador,
ambiência `seco`). Sem front-matter, é só a prosa.

## Como o K-NAR lê a sua história

Cada frase vira um de quatro tipos, automaticamente:

| Você escreve | Vira |
|---|---|
| `"..."` (entre aspas) | **DIÁLOGO** — uma fala de personagem |
| `perguntou Ana`, `gritou o Capitão` | o **locutor** e a emoção da fala anterior |
| `Passos numa poça d'água.` (frase curta de som) | **EFEITO SONORO** — o motor cria o som, o narrador **não** lê |
| `A floresta noturna zumbia.` (cenário) | **AMBIÊNCIA** — uma cama de fundo pela cena toda |
| o resto da prosa | **NARRAÇÃO** — lida pelo narrador (se houver) |

### Dicas para um bom resultado

- **Diálogo entre aspas** e a atribuição logo depois: `"Corram!", gritou ela.`
  O verbo (`gritou`/`sussurrou`) ajusta a atuação (grito vs. sussurro).
- **Som puro numa frase curta e sem nome de pessoa** vira efeito e não é narrado —
  ex.: `Um trovão ecoou.`, `Passos na poça.`. Se você mencionar um personagem
  (`Ana ouviu a porta ranger`), a frase é narrada **e** o efeito toca.
- **Cenário** (floresta, chuva, vento, motor, cidade, mar…) liga a ambiência.
- **Sem narrador** (`narrador: nao`): a história é contada só por vozes + sons —
  modo radiodrama. Aí evite frases de narração pura, prefira diálogo e som.

## Palavras que o K-NAR reconhece como som

Não é uma lista fechada — são as mais comuns por idioma (o resto vira narração):

- **Efeitos (pontuais):** tiro/disparo, explosão, porta que range, passos (e `poça`
  → splash), trovão, vidro que quebra, batida, sirene, alarme.
  *(EN: gunshot, explosion, creaked, footsteps/puddle, thunder…  ES: disparo,
  explosión, crujió, pasos/charco, trueno…)*
- **Ambiência (contínua):** floresta, chuva, vento, motor/nave, cidade, multidão,
  mar/ondas. *(EN: forest, rain, wind, engine/ship, city, crowd, ocean.  ES:
  bosque, lluvia, viento, motor, ciudad, multitud, mar.)*

## Gerar o áudio

```bash
# baixe as vozes do idioma (uma vez)
scripts/download_lang.sh pt        # ou en / es

# gere o audiobook
python -m k_nar minha_historia.md
python -m k_nar minha_historia.md --sem-narrador     # radiodrama
python -m k_nar minha_historia.md --idioma en        # sobrescreve o front-matter
```

Ou use a **interface web** (GitHub Pages) para enviar a história e receber o áudio
sem instalar nada — veja o README.
