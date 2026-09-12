<!-- source: documentation/guides/pytest.md blob 58aa4f70d42a | translated: 2026-09-12 | reviewed: - -->

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
  un archivo de traza — y, para markdown, un documento de escenario `.json`, `diagrams/<Clase>/<slug>.mmd`,
  y un artefacto `structural/<Clase>/<slug>.nt` libre de valores *(since 0.1.2, unreleased)* — bajo
  `NARRATIVETRACE_OUTPUT_DIR` (por defecto `narrative-traces`; añádelo a tu `.gitignore`, ver
  [que-commitear.md](que-commitear.md)). El resultado del escenario es `PASSED` o `FAILED`.
  Desactívalo con `NARRATIVETRACE_OUTPUT=false` (o `output = false` en un archivo de configuración,
  ver [guia-de-configuracion.md](guia-de-configuracion.md)). La versión publicada en PyPI,
  `narrativetrace-pytest==0.1.1`, todavía lo trae desactivado; en esa versión, activa
  `NARRATIVETRACE_OUTPUT=true` explícitamente.
- **Delta estructural + modo de aprobación** *(since 0.1.2, unreleased)* — el archivo `.nt` en disco
  es la última línea base en verde; el pie de la suite imprime un resumen `Since last green: …`, y
  el informe de una prueba que falla imprime su delta estructural en lugar de la traza completa
  cuando la forma cambió. Activa `NARRATIVETRACE_APPROVAL=true` para en su lugar hacer fallar una
  prueba contra una traza `.approved.nt` confirmada en el repositorio — consulta el
  [Formato de traza estructural](formato-de-traza-estructural.md) y la
  [Guía de configuración](guia-de-configuracion.md).
- **Pie de claridad** — el pie de la suite imprime una división `Clarity: X% high | Y% moderate |
  Z% low`, y (cuando la salida está habilitada) escribe `clarity-results.json` +
  `clarity-report.md` con una entrada por cada prueba trazada.

> Un id de `@pytest.mark.parametrize` (`test_finds_it[KAYAK]`) llega al *nombre de archivo* del
> artefacto que conserva valores y a su encabezado `scenario:`/`**Scenario:**`, y a
> `manifest.json`, exactamente igual que antes — nunca se recorta ni se oculta. El artefacto
> estructural `.nt` libre de valores es el único lugar donde esto *sí* está resuelto por ti: el
> encabezado estructural de una invocación se titula por el método y su índice de invocación,
> nunca por el id de parametrize *(since 0.1.2, unreleased)* — consulta el
> [Formato de traza estructural](formato-de-traza-estructural.md). Mantén los secretos fuera de
> los ids de `parametrize` de todos modos; consulta
> [Privacidad y ocultación § No garantías](privacidad-y-ocultacion.md#no-garantías).

## Niveles en las pruebas

`NARRATIVETRACE_LEVEL=OFF` no captura nada (árbol vacío); un valor desconocido degrada a `DETAIL`
sin error. El nivel también puede provenir de un archivo de configuración — el entorno simplemente
gana sobre él.
