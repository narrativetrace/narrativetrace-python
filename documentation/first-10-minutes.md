# See a trace in 60 seconds

No `logger.info(...)` lines, no test framework, nothing to open afterward — a plain script, one
run, and the trace prints straight to your terminal. Everything below was run for real against the
published package on PyPI (`narrativetrace` 0.1.1) — the output is pasted, not imagined.

## 1. New project, install the package

```bash
uv init myproject && cd myproject
uv add narrativetrace
```

## 2. The program

<!-- snippet: examples/sixty_seconds/main.py -->
```python
# main.py
from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, trace_object


class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


context = ContextVarNarrativeContext()
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

print(IndentedTextRenderer().render(context.capture_trace()))
```
<!-- /snippet -->

## 3. Run it

```bash
uv run main.py
```

<!-- snippet: examples/sixty_seconds/build/see_a_trace.txt mask=duration -->
```text
OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3) → "ORD-cust-1-prod-42-3" — 0ms
```
<!-- /snippet -->

`0ms` is real too — this call ran in under a millisecond. A slower machine or a heavier method
shows a larger number; the point is that it is measured, never faked.

You did not write a single log statement. That line came from the method name (`place_order`),
the parameter names (`customer_id`, `product_id`, `quantity`), and the actual return value — the
information your code already had.

## What just happened

- **`ContextVarNarrativeContext()`** is the capture context — where entered/returned/raised events
  land while your code runs. It threads through `contextvars`, so it follows async tasks and
  thread-pool work without you passing it around by hand.
- **`trace_object(OrderService(), context)`** wraps one real instance. Every public method call on
  the wrapper is captured; the object underneath is untouched — no base class, no decorator on
  `place_order` itself, no registration.
- **`context.capture_trace()` plus a renderer** turns the captured events into text.
  `IndentedTextRenderer` is what you just saw; `MarkdownRenderer` renders the same call as a
  Markdown bullet — the shape `narrativetrace-pytest` writes to disk by default — and
  `ProseRenderer` reads as a sentence. Same trace, three shapes.

## Send it to your logger

The console line is nice for a script; production wants the trace in the log stream you already
have. Route it through `LoggingTraceConsumer` — the stdlib `logging` bridge NarrativeTrace ships —
by giving the context an `EventStore` you can read back:

<!-- snippet: examples/sixty_seconds/main.py diff=examples/sixty_seconds/main_with_logger.py -->
```diff
 # main.py
-from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, trace_object
+import logging
+import sys
+
+from narrativetrace import (
+    ContextVarNarrativeContext,
+    IndentedTextRenderer,
+    LoggingTraceConsumer,
+    trace_object,
+)
+from narrativetrace.pipeline.event_store import EventStore
 
 
 class OrderService:
     def place_order(self, customer_id, product_id, quantity):
         return f"ORD-{customer_id}-{product_id}-{quantity}"
 
 
-context = ContextVarNarrativeContext()
+logging.basicConfig(level=logging.DEBUG, format="%(message)s", stream=sys.stdout)
+
+store = EventStore()
+context = ContextVarNarrativeContext(store=store)
 service = trace_object(OrderService(), context)
 service.place_order("cust-1", "prod-42", 3)
 
 print(IndentedTextRenderer().render(context.capture_trace()))
+
+consumer = LoggingTraceConsumer()
+for event in store.events():
+    consumer.accept(event)
```
<!-- /snippet -->

```bash
uv run main.py
```

<!-- snippet: examples/sixty_seconds/build/see_a_trace_with_logger.txt mask=duration -->
```text
OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3) → "ORD-cust-1-prod-42-3" — 0ms
→ OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3)
← returned: "ORD-cust-1-prod-42-3"
```
<!-- /snippet -->

(timing varies — `0ms` is whatever your machine measured, same as above.) The same trace now lands
in the sink you already have; the console line is untouched. `structlog` users get the identical
key set from `narrativetrace-structlog` instead — see the full [Logging Guide](guides/logging.md)
for `NarrativeContextFilter`, MDC keys, and request-scoped correlation.

## Next

| You want | Go to |
|---|---|
| Traces from your test suite instead of a script | [pytest Guide](guides/pytest.md) |
| Keep a value out of the trace | [Privacy and Redaction](privacy-and-redaction.md) |
| A naming-clarity score for this code | [Clarity Guide](guides/clarity.md) |
| Tracing levels, output settings, precedence | [Configuration Guide](guides/configuration.md) |
| Something above did not work as shown | [Troubleshooting](troubleshooting.md) |
