<!-- source: documentation/guides/installation.md blob 625a9fe01d77 | translated: 2026-09-12 | reviewed: - -->

# Instalação

O NarrativeTrace tem como alvo o Python ≥ 3.12 e é distribuído como um conjunto de pacotes: um core sem dependências de terceiros
mais integrações opcionais.

```bash
uv add narrativetrace                 # somente o core
uv add narrativetrace-pytest          # plugin do pytest (traz core + diagrams)
uv add narrativetrace-diagrams        # renderizadores Mermaid / PlantUML
uv add narrativetrace-otel            # ponte com o OpenTelemetry (opentelemetry-api)
uv add narrativetrace-asgi            # middleware do Starlette/FastAPI
uv add narrativetrace-clarity         # motor de clareza de nomes + gate de CLI
uv add narrativetrace-structlog       # processador de structlog
uv add narrativetrace-glossary        # glossário de domínio + tradução de traces
```

`pip install narrativetrace` funciona da mesma forma. Adicione somente as integrações que você usa — o core
não carrega dependências de terceiros. Todos os pacotes acima estão no PyPI.

`narrativetrace-structlog` traz `structlog` como dependência própria, então
`uv add narrativetrace-structlog` é tudo de que o processador precisa — sem um
`uv add structlog` à parte.

## A partir deste repositório (workspace)

Necessário apenas para trabalhar no próprio NarrativeTrace, não para usá-lo:

```bash
uv sync --all-packages     # instala todos os pacotes do workspace em modo editável
uv run poe check           # roda o gate de qualidade completo
```
