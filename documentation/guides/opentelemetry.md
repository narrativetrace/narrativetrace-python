# OpenTelemetry

`narrativetrace-otel` emits your narrative as OpenTelemetry spans — the human trace and the
backend correlation from one capture. It depends only on `opentelemetry-api`.

## Batch export (completed tree)

```python
from opentelemetry import trace
from narrativetrace_otel import TraceSpanExporter

TraceSpanExporter(trace.get_tracer("orders")).export(context.capture_trace().roots)
```

Each node becomes a nested span with `narrative.class`/`narrative.method`, typed
`narrative.param.<name>` attributes, `narrative.outcome`, `narrative.duration_ms`, concurrency
attributes, and `nt.*` schema attributes on **every** span.

## Live streaming (span per event)

Attach `OtelTraceEventListener` to the pipeline to open a span on each enter and close it on the
matching exit, anchored to the **event timestamps** (not processing time). Orphaned spans (enter
without exit) are evicted by a bounded `PerishableMap` and ended with an error status.

```python
from narrativetrace_otel import OtelTraceEventListener

listener = OtelTraceEventListener(trace.get_tracer("orders"))
# feed it TraceEvents from the capture pipeline
```

## Attribute vocabulary

Trace-level keys (root spans only): `narrative.service.name/version/environment`,
`narrative.http.method/route`, `narrative.client_ip`, `narrative.enduser.id`,
`narrative.session.id`, `narrative.tenant.id`. Identity + `nt.entryType`/`nt.schemaVersion` appear
on every span so any span is independently correlatable.
