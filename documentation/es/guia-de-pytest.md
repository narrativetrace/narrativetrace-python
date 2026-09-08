<!-- source: documentation/guides/pytest.md blob 633109ebae77 | translated: 2026-09-03 | reviewed: 2026-09-03 -->

# Guía de pytest

`narrativetrace-pytest` se registra automáticamente (punto de entrada). Solicita el fixture
`narrative_trace` para obtener un contexto de captura nuevo en cada prueba.

```python
from narrativetrace import trace_object

def test_place_order(narrative_trace):
    service = trace_object(OrderService(narrative_trace), narrative_trace)
    service.place_order("cust-1", "prod-42", 3)
```

## Qué obtienes

- **Narrativas de fallo** — una prueba que falla imprime un bloque enmarcado `Scenario: …` con la
  traza de ejecución indentada, de modo que la ruta de llamadas *es* el diagnóstico.
- **Advertencias de plantilla** — los tokens `@narrated`/`@on_error` sin resolver se reportan una
  vez por ejecución.
- **Artefactos** — con `NARRATIVETRACE_OUTPUT=1` (o `output = true` en un archivo de configuración,
  ver [guia-de-configuracion.md](guia-de-configuracion.md)), cada prueba no vacía escribe un
  archivo de traza — y, para markdown, un documento de escenario `.json` más
  `diagrams/<Clase>/<slug>.mmd` — bajo `NARRATIVETRACE_OUTPUT_DIR`. El resultado del escenario es
  `PASSED` o `FAILED`.
- **Pie de claridad** — el pie de la suite imprime una división `Clarity: X% high | Y% moderate |
  Z% low`, y (cuando la salida está habilitada) escribe `clarity-results.json` +
  `clarity-report.md` con una entrada por cada prueba trazada.

## Niveles en las pruebas

`NARRATIVETRACE_LEVEL=OFF` no captura nada (árbol vacío); un valor desconocido degrada a `DETAIL`
sin error. El nivel también puede provenir de un archivo de configuración — el entorno simplemente
gana sobre él.
