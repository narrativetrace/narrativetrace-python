# narrativetrace-otel

OpenTelemetry span bridge for [narrativetrace](../narrativetrace) traces.

Two entry points:

* `OtelTraceEventListener` — a live event consumer that opens a span on each enter and
  closes it on the matching exit, anchored to the **event timestamps** (not processing
  time). Orphaned spans are evicted by a bounded `PerishableMap`.
* `TraceSpanExporter` — a batch exporter that walks a completed `TraceTree`/`TraceNode`
  forest and emits a nested span per node.
