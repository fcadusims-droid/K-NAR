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
pessoa: terceira      # terceira | primeira | auto  (quem conta a história)
protagonista:         # em 1ª pessoa: o nome de quem narra (opcional)
ambientacao: cockpit_metalico_eco
---

A nave cortava o vazio, e o zumbido dos motores enchia a ponte.
Uma porta blindada rangeu. "Tem alguém aí?", perguntou a Comandante, tensa.
Ninguém respondeu. Então um tiro disparou nas sombras.
"Todos em posição!", ela gritou.
```

Todos os campos do front-matter são opcionais (defaults: `pt`, com narrador,
`pessoa: auto`, ambiência `seco`). Sem front-matter, é só a prosa.

> **Dois modelos prontos:** `examples/template_terceira_pessoa.md` (narrador conta) e
> `examples/template_primeira_pessoa.md` (o protagonista conta). Copie o que combina
> com a sua história.

## Como o K-NAR lê a sua história

Cada frase vira um de quatro tipos, automaticamente:

| Você escreve | Vira |
|---|---|
| `"..."` (entre aspas) | **DIÁLOGO** — uma fala de personagem |
| `perguntou Ana`, `gritou o Capitão` | o **locutor** e a emoção da fala anterior |
| `Passos numa poça d'água.` (frase curta de som) | **EFEITO SONORO** — o motor cria o som, o narrador **não** lê |
| `A floresta noturna zumbia.` (cenário) | **AMBIÊNCIA** — uma cama de fundo pela cena toda |
| o resto da prosa | **NARRAÇÃO** — lida pelo narrador (se houver) |

### Quem conta: 3ª pessoa vs 1ª pessoa

- **3ª pessoa** (`pessoa: terceira`) — um **narrador de fora** conta ("*ele* entrou…").
  No áudio o narrador tem voz própria e é **seco/íntimo**: não está na cena, está te
  contando. É o padrão.
- **1ª pessoa** (`pessoa: primeira`) — o **protagonista** conta ("*eu* entrei…"). A
  narração usa a **mesma voz** dele (diga `protagonista: Nome` para casar com as falas)
  e, por ele estar **dentro da cena**, ganha o **eco do cômodo** onde ele está — você
  ouve pelos ouvidos dele.
- `pessoa: auto` (padrão) — o K-NAR detecta contando "eu/meu" vs "ele/ela" na narração.

### Vozes por aparência (elenco automático)

O K-NAR **escolhe a voz de cada personagem** pela descrição na prosa — não só
"homem/mulher", mas **idade, gênero e timbre**. Descreva o personagem quando ele
aparece: *"o **velho** de voz **rouca**"* → voz grave e lenta; *"a **menina**"* → voz
aguda e ágil; *"a **jovem**"*, *"o **senhor**"*, etc. Sem descritor, ele recebe uma voz
adulta neutra (ainda distinta das outras). O gênero vem dos **descritores**, nunca de
adivinhar pelo nome.

### Distância e lugar (o "set virtual" de zonas)

O K-NAR entende **de onde** o som vem e monta um **set acústico** da cena:

- **Distância:** "tiros **ao longe**" soam baixos e abafados (o ar come os agudos) e
  mais centrais; "um tiro **à queima-roupa**" soa alto, seco e largo. Palavras como
  *ao longe / distante / no horizonte* e *perto / ao lado / queima-roupa* controlam isso.
- **Cômodos (zonas):** mencione os lugares por onde a cena passa — *cozinha, sala,
  corredor, porão, quintal…* — e o K-NAR monta um **mapa da casa**. O **eco segue o
  personagem** de cômodo em cômodo (a sala grande ecoa, o quintal é aberto e seco), e
  uma voz do **cômodo ao lado** soa **abafada** (a parede come os agudos). Isso liga
  sozinho quando há **2+ cômodos**; desligue com `--sem-espaco`.
- **Espaço fixo:** para uma cena única, fixe o eco no front-matter:
  `ambientacao: galpao_vazio` (ou *catedral, caverna, túnel, banheiro…*).

### Dicas para um bom resultado

- **Diálogo entre aspas** `"..."` **ou travessão** `— Fala — disse Fulano` (padrão
  literário em PT). O verbo (`gritou`/`sussurrou`) ajusta a atuação (grito vs. sussurro).
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

# baixe a biblioteca de EFEITOS SONOROS reais (ESC-50, CC0) — uma vez
python scripts/download_sfx.py     # (--free-only p/ só CC0/CC-BY; senão, síntese)

# gere o audiobook (usa sounds/ automaticamente se existir)
python -m k_nar minha_historia.md
python -m k_nar minha_historia.md --sem-narrador     # radiodrama
python -m k_nar minha_historia.md --idioma en        # sobrescreve o front-matter
```

Ou use a **interface web** (GitHub Pages) para enviar a história e receber o áudio
sem instalar nada — veja o README.
