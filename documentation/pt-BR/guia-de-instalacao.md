<!-- source: documentation/guides/installation.md blob 080622673a09 | translated: 2026-09-07 | reviewed: - -->

# Instalação

O NarrativeTrace tem como alvo o Python ≥ 3.12 e é distribuído como um conjunto de pacotes: um core sem dependências
mais integrações opcionais.

```bash
uv add narrativetrace                 # somente o core
uv add narrativetrace-pytest          # plugin do pytest (traz core + diagrams)
uv add narrativetrace-diagrams        # renderizadores Mermaid / PlantUML
uv add narrativetrace-otel            # ponte com o OpenTelemetry (opentelemetry-api)
uv add narrativetrace-asgi            # middleware do Starlette/FastAPI
uv add narrativetrace-clarity         # motor de clareza de nomes + gate de CLI
uv add narrativetrace-structlog       # processador de structlog
```

`pip install narrativetrace` funciona da mesma forma. Adicione somente as integrações que você usa — o core
não carrega dependências de terceiros.

A publicação no PyPI ainda não foi feita — até que os pacotes estejam no índice, instale a partir
de um checkout deste repositório, abaixo.

## A partir deste repositório (workspace)

```bash
uv sync --all-packages     # instala todos os pacotes do workspace em modo editável
uv run poe check           # roda o gate de qualidade completo
```
