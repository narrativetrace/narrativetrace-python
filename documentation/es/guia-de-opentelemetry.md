<!-- source: documentation/guides/opentelemetry.md blob 8c80d624163c | translated: 2026-09-03 | reviewed: 2026-09-03 -->

# OpenTelemetry

`narrativetrace-otel` emite tu narrativa como spans de OpenTelemetry — la traza legible por
humanos y la correlación con el backend a partir de una sola captura. Depende únicamente de
`opentelemetry-api`.

## Exportación por lotes (árbol completado)

```python
from opentelemetry import trace
from narrativetrace_otel import TraceSpanExporter

TraceSpanExporter(trace.get_tracer("orders")).export(context.capture_trace().roots)
```

Cada nodo se convierte en un span anidado con atributos `narrative.class`/`narrative.method`,
atributos tipados `narrative.param.<name>`, `narrative.outcome`, `narrative.duration_ms`,
atributos de concurrencia y atributos de esquema `nt.*` en **cada** span.

## Streaming en vivo (un span por evento)

Conecta `OtelTraceEventListener` al pipeline para abrir un span en cada entrada y cerrarlo en la
salida correspondiente, anclado a las **marcas de tiempo del evento** (no al tiempo de
procesamiento). Los spans huérfanos (entrada sin salida) son desalojados por un `PerishableMap`
acotado y finalizados con un estado de error.

```python
from narrativetrace_otel import OtelTraceEventListener

listener = OtelTraceEventListener(trace.get_tracer("orders"))
# aliméntalo con TraceEvents provenientes del pipeline de captura
```

## Vocabulario de atributos

Claves a nivel de traza (solo spans raíz): `narrative.service.name/version/environment`,
`narrative.http.method/route`, `narrative.client_ip`, `narrative.enduser.id`,
`narrative.session.id`, `narrative.tenant.id`. La identidad y `nt.entryType`/`nt.schemaVersion`
aparecen en cada span, de modo que cualquier span sea correlacionable de forma independiente.
