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

## Estado atual (MVP)

Já implementado, **rodando 100% offline e sem dependências** (só stdlib):

- `Orquestrador` — as passagens 2 e 3.
- `TimingPolicy` — a matriz que traduz metadados relativos em milissegundos, com
  guardas de inteligibilidade (uma interrupção nunca engole a fala inteira).
- `TTSBackend` — contrato agnóstico; `MockTTSBackend` para testar sem motor de voz.
- `Timeline` — a Edit Decision List que o DSP vai consumir.

Ainda **não** existe: backend XTTS real, camada de DSP (reverb/panning) e o prompt
do LLM. Ver "próximos passos" na doc de arquitetura.

## Rodar

```bash
# demo: carrega uma cena e imprime a linha de tempo
python -m examples.run_mvp

# testes (provam que a mesma agressividade escala com a duracao real)
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
