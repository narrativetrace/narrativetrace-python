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

`main.py` adopts one fixed trace id — the same mechanism a servlet-style boundary uses for an
inbound trace header — purely so this page's output always names the same trace. Your own code
never does this: a real run generates a random trace id every time, and the three-word name below
is derived from it, never from a name you choose.

<!-- snippet: examples/sixty_seconds/main.py -->
```python
# main.py
from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, TraceId, trace_object


class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


# snippet:begin fixedTraceId
# A fixed trace id, adopted so this page's embedded output always names the same trace. A real
# run generates a random one every time (never this -- it is this DEMO's own constant, not the
# library default) via the same TraceId.adopt_trace_id a servlet-style boundary uses for an
# inbound trace header.
DEMO_TRACE_ID = TraceId("a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4")

# snippet:end fixedTraceId

context = ContextVarNarrativeContext()
context.adopt_trace_id(DEMO_TRACE_ID)
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
trace: loose hook parks (a1b2c3d)

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
have. `export_to_logger` sends an already-captured trace to your logger in one call *(since 0.1.2,
unreleased)* — the stdlib `logging` bridge NarrativeTrace ships; on published `0.1.1` itself,
replay `store.events()` through `LoggingTraceConsumer` by hand instead):

<!-- snippet: examples/sixty_seconds/main.py diff=examples/sixty_seconds/main_with_logger.py -->
```diff
 # main.py
-from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, TraceId, trace_object
+import logging
+import sys
+
+from narrativetrace import (
+    ContextVarNarrativeContext,
+    IndentedTextRenderer,
+    NarrativeContextFilter,
+    TraceId,
+    export_to_logger,
+    trace_object,
+)
 
 
 class OrderService:
     def place_order(self, customer_id, product_id, quantity):
         return f"ORD-{customer_id}-{product_id}-{quantity}"
 
 
 # snippet:begin fixedTraceId
 # A fixed trace id, adopted so this page's embedded output always names the same trace. A real
 # run generates a random one every time (never this -- it is this DEMO's own constant, not the
 # library default) via the same TraceId.adopt_trace_id a servlet-style boundary uses for an
 # inbound trace header.
 DEMO_TRACE_ID = TraceId("a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4")
 
 # snippet:end fixedTraceId
 
+handler = logging.StreamHandler(sys.stdout)
+handler.addFilter(NarrativeContextFilter())
+logging.basicConfig(
+    level=logging.DEBUG, format="[%(traceName)s] [%(runName)s] %(message)s", handlers=[handler]
+)
+
 context = ContextVarNarrativeContext()
 context.adopt_trace_id(DEMO_TRACE_ID)
 service = trace_object(OrderService(), context)
 service.place_order("cust-1", "prod-42", 3)
 
-print(IndentedTextRenderer().render(context.capture_trace()))
+trace = context.capture_trace()
+print(IndentedTextRenderer().render(trace))
+
+export_to_logger(trace)
```
<!-- /snippet -->

```bash
uv run main.py
```

<!-- snippet: examples/sixty_seconds/build/see_a_trace_with_logger.txt mask=duration,traceName -->
```text
trace: loose hook parks (a1b2c3d)

OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3) → "ORD-cust-1-prod-42-3" — 0ms
[mossy burr coats] [] → OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3)
[mossy burr coats] [] ← returned: "ORD-cust-1-prod-42-3"
```
<!-- /snippet -->

(timing varies — `0ms` is whatever your machine measured, same as above; the phrase in brackets
varies too — `export_to_logger` replays the trace through its own fresh id, unrelated to the fixed
one above.) `traceName` is populated because a trace is active; `runName` is empty here because
this plain script belongs to no test-suite execution — it populates only under the
`narrativetrace-pytest` fixture (see [Configuration Guide, § The run has a
name](guides/configuration.md#the-run-has-a-name)). The same trace now lands in the sink you
already have; the console line is untouched. `structlog` users get the identical key set from
`narrativetrace-structlog` instead — see the full [Logging Guide](guides/logging.md) for
`NarrativeContextFilter`, MDC keys, and request-scoped correlation.

## Next

| You want | Go to |
|---|---|
| Traces from your test suite instead of a script | [pytest Guide](guides/pytest.md) |
| Keep a value out of the trace | [Privacy and Redaction](privacy-and-redaction.md) |
| A naming-clarity score for this code | [Clarity Guide](guides/clarity.md) |
| Tracing levels, output settings, precedence | [Configuration Guide](guides/configuration.md) |
| Something above did not work as shown | [Troubleshooting](troubleshooting.md) |
