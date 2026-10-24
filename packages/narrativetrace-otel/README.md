# narrativetrace-otel

OpenTelemetry span bridge for [narrativetrace](../narrativetrace) traces.

Two entry points:

* `OtelTraceEventListener` — a live event consumer that opens a span on each enter and
  closes it on the matching exit, anchored to the **event timestamps** (not processing
  time). Orphaned spans are evicted by a bounded `PerishableMap`.
* `TraceSpanExporter` — a batch exporter that walks a completed `TraceTree`/`TraceNode`
  forest and emits a nested span per node.

### Matching span ids

Build your tracer provider with the helper. `tracer_provider()` returns a `TracerProvider` with
`NarrativeTraceIdGenerator` installed; every other keyword passes through:

```python
from narrativetrace_otel import tracer_provider

provider = tracer_provider(set_global=True)
```

A span's OpenTelemetry id is then its NarrativeTrace id, and a child that starts after its parent has
ended parents on the real parent. The same effect without the helper is the one-liner
`TracerProvider(id_generator=NarrativeTraceIdGenerator())`, or `OTEL_PYTHON_ID_GENERATOR=narrativetrace`
under auto-instrumentation. An `id_generator` you pass yourself is kept (with one warning that ids will
not mirror). Opt out with `mirror_ids=False` or `NARRATIVETRACE_OTEL_MIRROR_IDS=false`. Export each
trace through one path (the live listener or `TraceSpanExporter`), not both.
