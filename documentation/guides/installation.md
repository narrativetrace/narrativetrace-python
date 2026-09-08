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
```

`pip install narrativetrace` works the same way. Only add the integrations you use — the core
carries no third-party dependencies.

PyPI publication is not done yet — until the packages are on the index, install from a checkout
of this repository, below.

## From this repository (workspace)

```bash
uv sync --all-packages     # install every workspace package in editable mode
uv run poe check           # run the full quality gate
```
