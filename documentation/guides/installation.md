# Installation

NarrativeTrace targets Python ≥ 3.12 and is distributed as a set of packages: a dependency-free
core plus optional integrations.

```bash
uv add narrativetrace                 # core only
uv add narrativetrace-pytest          # pytest plugin (pulls in core + diagrams)
uv add narrativetrace-diagrams        # Mermaid / PlantUML renderers
uv add narrativetrace-otel            # OpenTelemetry bridge (opentelemetry-api)
uv add narrativetrace-asgi            # Starlette/FastAPI middleware
uv add narrativetrace-clarity         # naming-clarity engine + CLI gate
uv add narrativetrace-structlog       # structlog processor
uv add narrativetrace-glossary        # domain glossary + trace translation
```

`pip install narrativetrace` works the same way. Only add the integrations you use — the core
carries no third-party dependencies. Every package above is on PyPI, published at `0.1.1`.

`narrativetrace-structlog` pulls in `structlog` itself *(since 0.1.2, unreleased)* — on PyPI's
published `0.1.1` it is an optional extra, so `uv add narrativetrace-structlog` alone does not
install `structlog`; add it explicitly (`uv add structlog`) on that version.

## From this repository (workspace)

Only needed to work on NarrativeTrace itself, not to use it:

```bash
uv sync --all-packages     # install every workspace package in editable mode
uv run poe check           # run the full quality gate
```
