<!-- source: documentation/guides/pytest.md blob a44c1857df02 | translated: 2026-09-12 | reviewed: - -->

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
- **Artefactos** — activados por defecto *(since 0.1.2, unreleased)*: cada prueba no vacía escribe
  un archivo de traza — y, para markdown, un documento de escenario `.json` más
  `diagrams/<Clase>/<slug>.mmd` — bajo `NARRATIVETRACE_OUTPUT_DIR` (por defecto `narrative-traces`;
  añádelo a tu `.gitignore`, ver [que-commitear.md](que-commitear.md)). El resultado del escenario
  es `PASSED` o `FAILED`. Desactívalo con `NARRATIVETRACE_OUTPUT=false` (o `output = false` en un
  archivo de configuración, ver [guia-de-configuracion.md](guia-de-configuracion.md)). La versión
  publicada en PyPI, `narrativetrace-pytest==0.1.1`, todavía lo trae desactivado; en esa versión,
  activa `NARRATIVETRACE_OUTPUT=true` explícitamente.
- **Pie de claridad** — el pie de la suite imprime una división `Clarity: X% high | Y% moderate |
  Z% low`, y (cuando la salida está habilitada) escribe `clarity-results.json` +
  `clarity-report.md` con una entrada por cada prueba trazada.

> Un id de `@pytest.mark.parametrize` (`test_finds_it[KAYAK]`) llega tanto al *nombre de archivo*
> del artefacto como al encabezado `scenario:`/`**Scenario:**` — nunca se recorta ni se oculta. El
> único artefacto que escribe este plugin es del tipo que conserva valores (ver
> [Guía de funcionalidades](guia-de-funcionalidades.md): un artefacto estructural libre de
> valores, al que el contrato multiplataforma de nombrado titularía sin el id de `parametrize`,
> todavía no tiene equivalente en Python). Mantén los secretos fuera de los ids de `parametrize`;
> consulta [Privacidad y ocultación § No garantías](privacidad-y-ocultacion.md#no-garantías).

## Niveles en las pruebas

`NARRATIVETRACE_LEVEL=OFF` no captura nada (árbol vacío); un valor desconocido degrada a `DETAIL`
sin error. El nivel también puede provenir de un archivo de configuración — el entorno simplemente
gana sobre él.
