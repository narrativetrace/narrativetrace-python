<!-- source: documentation/guides/installation.md blob 080622673a09 | translated: 2026-09-07 | reviewed: - -->

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
```

`pip install narrativetrace` funciona igual. Añade solo las integraciones que uses — el núcleo
no lleva dependencias de terceros.

La publicación en PyPI todavía no está hecha — hasta que los paquetes estén en el índice,
instálalos desde una copia de este repositorio, abajo.

## Desde este repositorio (workspace)

```bash
uv sync --all-packages     # instala todos los paquetes del workspace en modo editable
uv run poe check           # ejecuta la puerta de calidad completa
```
