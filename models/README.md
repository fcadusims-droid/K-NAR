# Modelos (LLM + vozes)

Este diretório guarda os pesos que o K-NAR usa em tempo de execução. **Os binários
não são versionados no git** — e isso é intencional, não uma limitação de preguiça:

- O GitHub **rejeita arquivos acima de 100 MB**. O GGUF do LLM tem ~1,1 GB.
- Git LFS resolveria, mas 1,1 GB estoura a cota grátis (1 GB) do LFS.
- Pesos de modelo mudam de fonte/versão; o correto é o repo **especificar e buscar**,
  não carregar o binário. Assim `git clone` fica leve e a origem fica auditável.

O repositório é **totalmente reprodutível**: o código (gerador de áudio, Orquestrador,
Director) está todo versionado, e um comando baixa os pesos.

## Baixar tudo

```bash
scripts/setup.sh --llm     # deps + voz Piper + llama-cpp + LLM (~1.2GB no total)
```

Ou individualmente:

```bash
scripts/download_piper.sh  # voz neural PT-BR (Piper, ~63MB)
scripts/download_model.sh  # LLM do Director (Qwen2.5-1.5B GGUF, ~1.1GB)
```

## O que vai aqui depois de baixar

```
models/
├── qwen2.5-1.5b-instruct-q4_k_m.gguf     # LLM do Director (PASSAGEM 1)
└── piper/
    ├── pt_BR-faber-medium.onnx           # voz neural (PASSAGEM 2)
    └── pt_BR-faber-medium.onnx.json
```

## Se você REALMENTE quiser versionar os pesos

Use Git LFS por sua conta e risco (custo de cota):

```bash
git lfs install
git lfs track "*.gguf" "*.onnx"
git add .gitattributes models/
```

Não recomendado: infla o repo e o clone para todos.
