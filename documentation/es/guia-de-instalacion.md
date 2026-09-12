<!-- source: documentation/guides/installation.md blob 6155e178c221 | translated: 2026-09-12 | reviewed: - -->

# Instalación

NarrativeTrace apunta a Python ≥ 3.12 y se distribuye como un conjunto de paquetes: un núcleo sin dependencias
más integraciones opcionales.

```bash
uv add narrativetrace                 # solo core
uv add narrativetrace-pytest          # plugin de pytest (incluye core + diagrams)
uv add narrativetrace-diagrams        # renderizadores de Mermaid / PlantUML
uv add narrativetrace-otel            # puente con OpenTelemetry (opentelemetry-api)
uv add narrativetrace-asgi            # middleware de Starlette/FastAPI
uv add narrativetrace-clarity         # motor de claridad de nombres + puerta de CLI
uv add narrativetrace-structlog       # procesador de structlog
uv add narrativetrace-glossary        # glosario de dominio + traducción de trazas
```

`pip install narrativetrace` funciona igual. Añade solo las integraciones que uses — el núcleo
no lleva dependencias de terceros. Todos los paquetes de arriba están en PyPI, publicados en la
versión `0.1.1`.

`narrativetrace-structlog` incluye `structlog` como dependencia propia *(since 0.1.2,
unreleased)* — en la versión publicada en PyPI, `0.1.1`, es un extra opcional, así que
`uv add narrativetrace-structlog` por sí solo no instala `structlog`; añádelo explícitamente
(`uv add structlog`) en esa versión.

## Desde este repositorio (workspace)

Solo necesario para trabajar en NarrativeTrace mismo, no para usarlo:

```bash
uv sync --all-packages     # instala todos los paquetes del workspace en modo editable
uv run poe check           # ejecuta la puerta de calidad completa
```
