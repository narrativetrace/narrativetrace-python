<!-- source: documentation/guides/installation.md blob 625a9fe01d77 | translated: 2026-09-12 | reviewed: - -->

# Instalación

NarrativeTrace apunta a Python ≥ 3.12 y se distribuye como un conjunto de paquetes: un núcleo sin
dependencias de terceros más integraciones opcionales.

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
no lleva dependencias de terceros. Todos los paquetes de arriba están en PyPI.

`narrativetrace-structlog` incluye `structlog` como dependencia propia, así que
`uv add narrativetrace-structlog` es todo lo que necesita el procesador — sin un
`uv add structlog` aparte.

## Desde este repositorio (workspace)

Solo necesario para trabajar en NarrativeTrace mismo, no para usarlo:

```bash
uv sync --all-packages     # instala todos los paquetes del workspace en modo editable
uv run poe check           # ejecuta la puerta de calidad completa
```
