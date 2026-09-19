# Logging, structlog & Loguru

NarrativeTrace bridges to the stdlib `logging` framework and to `structlog`, emitting the *same*
canonical correlation keys from both. A Loguru user reaches the same trace through Loguru's own
documented stdlib interop — see [Loguru](#loguru) below.

## stdlib logging

Two pieces:

- `LoggingTraceConsumer` — an event consumer that logs enter/return at `DEBUG` and exceptions at
  `WARNING` (`!! {type}: {message} [{error_context}]`, control-sanitised).
- `NarrativeContextFilter` — a logging `Filter` that stamps the current scope's keys (`traceId`,
  `traceName`, `spanId`, `nt.class`, `nt.method`, `nt.depth`, service identity, request/user keys)
  onto every record. `traceName` and `runName` *(since 0.1.2)* are always present once
  the filter has touched a record — `""` when no trace/run is active — so a pattern referencing
  either never raises on an untraced line.

```python
import logging
from narrativetrace import NarrativeContextFilter

handler = logging.StreamHandler()
handler.addFilter(NarrativeContextFilter())
logging.getLogger().addHandler(handler)
```

## One consumer per stream, many handlers

`nt.depth` is a private counter on each `LoggingTraceConsumer` instance *(since 0.1.2)*, so two of them replaying the *same* event stream (say, both attached as listeners on
one pipeline) each report their own correct depth — one no longer corrupts the other's count.
`NarrativeContextFilter` and the
`structlog` processor are unaffected either way: they read the shared class/method/trace identity
of the innermost frame, which is the same for every instance processing one event, never a
consumer's own depth counter. Prefer one `LoggingTraceConsumer` per event stream regardless — it
is simpler to reason about, and a stray second instance is easy to create by accident (e.g. two
different pieces of setup code each constructing their own). Want the trace in more than one place
(stdout and a file, say)? Add more `logging.Handler`s to its logger instead of a second consumer:

```python
logger = logging.getLogger("narrativetrace")
logger.addHandler(logging.StreamHandler())           # first destination
logger.addHandler(logging.FileHandler("trace.log"))  # second destination, same consumer
```

## `export_to_logger` — one call

*(since 0.1.2)* — on PyPI's published `0.1.1`, replay `store.events()` through a
`LoggingTraceConsumer` by hand instead.

`export_to_logger(trace, logger=None)` replays an already-captured `TraceTree` through a private
`LoggingTraceConsumer` in one call — no `EventStore` to wire up, no loop to write by hand:

```python
from narrativetrace import ContextVarNarrativeContext, export_to_logger, trace_object

context = ContextVarNarrativeContext()
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

export_to_logger(context.capture_trace())
```

Each call opens its own private consumer, so calling it more than once — even concurrently, from
different threads — never trips the one-consumer-per-stream rule above.

## Request-level scope

Inside an HTTP request the ASGI middleware opens a `request_log_scope(...)` so request keys
(`httpMethod`, `httpRoute`, `clientIp`, user identity) ride along beneath any active method scope.

## The run has its own MDC key: `runName`

*(since 0.1.2)* `narrativetrace-pytest`'s `pytest_sessionstart` hook generates one
run id per pytest session — never re-derived — and calls `set_run_name(run.name)` so `runName`
(the run's own three-word phrase, distinct from any trace's `traceName`) rides along on every log
line for the whole session, the same way `request_log_scope` rides beneath a method scope; the
matching `pytest_sessionfinish` hook clears it. A pattern showing both keys:

```python
import logging

logging.basicConfig(format="%(asctime)s [%(traceName)s] [%(runName)s] %(message)s")
```

`runName` is `""` outside a tracked pytest session — a plain script, or `export_to_logger` called
from one — so the same pattern is safe everywhere. See [Configuration Guide, § The run has a
name](configuration.md#the-run-has-a-name) for where else the run name appears (the suite footer,
`manifest.json`, every Markdown trace document's frontmatter) and its invariant: it never reaches
the structural `.nt` artifact.

## structlog

`narrativetrace-structlog` provides a processor that injects the identical key set:

```python
import structlog
from narrativetrace_structlog import narrative_context_processor

structlog.configure(
    processors=[narrative_context_processor, structlog.processors.JSONRenderer()]
)
```

Both front-ends share `narrativetrace.current_scope_keys()` as the single source of vocabulary, so
their key sets can never drift.

## Loguru

NarrativeTrace ships no Loguru-specific bridge — Loguru is a logger, not a source of narration,
and the stdlib bridge above is the whole mechanism a Loguru user needs. Loguru documents its own
interop with stdlib `logging`: an `InterceptHandler` that subclasses `logging.Handler` and
re-logs every stdlib record through `logger` (see Loguru's own recipe, ["Entirely compatible with
standard logging"](https://loguru.readthedocs.io/en/stable/overview.html)). Point the stdlib root
logger at that handler and `export_to_logger` — the same one-call replay from [the 60-second
tutorial's "Send it to your logger" step](../sixty-seconds.md#send-it-to-your-logger) — reaches
your Loguru sink with no NarrativeTrace-specific code at all:

<!-- snippet: examples/sixty_seconds/main_with_loguru.py -->
```python
# main.py
import inspect  # new: InterceptHandler's own frame-walk, verbatim from Loguru's recipe
import logging  # new: the stdlib logger InterceptHandler subclasses; export_to_logger's target
import sys  # new: stdout target for the loguru sink below

from loguru import logger  # new: the destination sink

from narrativetrace import (
    ContextVarNarrativeContext,
    IndentedTextRenderer,
    TraceId,
    export_to_logger,  # new: replays an already-captured trace through your logger, one call
    trace_object,
)


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


# snippet:begin interceptHandler
# new: Loguru's own documented stdlib-interop recipe, verbatim -- see
# https://loguru.readthedocs.io/en/stable/overview.html, "Entirely compatible with standard
# logging". NarrativeTrace ships no Loguru-specific bridge; this recipe is the whole mechanism --
# every record a stdlib logger emits (export_to_logger's included) is re-logged through `logger`.
class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists.
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message.
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# snippet:end interceptHandler

# new: a fixed, timestamp-free sink so this page's embedded output never varies by wall clock --
# your own sink keeps its real format, colours, and rotation; only this demo needs determinism.
logger.remove()
logger.add(sys.stdout, format="{level} | {message}", colorize=False)
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

context = ContextVarNarrativeContext()
context.adopt_trace_id(DEMO_TRACE_ID)
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

trace = context.capture_trace()  # new: capture once, reuse for both the print and the export
print(IndentedTextRenderer().render(trace))

export_to_logger(trace)  # new: the same one-call export from step 2 -- now landing in Loguru
```
<!-- /snippet -->

```bash
uv run main.py
```

<!-- snippet: examples/sixty_seconds/build/see_a_trace_with_loguru.txt mask=duration -->
```text
trace: loose hook parks (a1b2c3d)

OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3) → "ORD-cust-1-prod-42-3" — 0ms
DEBUG | → OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3)
DEBUG | ← returned: "ORD-cust-1-prod-42-3"
```
<!-- /snippet -->

(the demo sink's `format="{level} | {message}"` is this page's own choice, for output that never
varies by wall clock; your real sink keeps whatever format, colours, and rotation you already
configured.) A Loguru user keeps everything Loguru already gives them — sinks, rotation, colours,
`logger.catch` — completely untouched; `export_to_logger` only replays an already-captured trace
through the stdlib bridge Loguru's `InterceptHandler` is already listening to. What they stop
writing is the `logger.info(...)` (or `logger.debug(...)`) call inside the business method
itself — the two lines above came from `place_order`'s own name, parameter names, and return
value, the information the code already had, not from a call anyone wrote.

## Where this is wired in the examples

Every runnable example under `examples/` sends its trace to a realistically configured logger
alongside its console narration — `logging.basicConfig` in the composition root plus
`LoggingTraceConsumer`/`NarrativeContextFilter` from this guide, not a snippet copied into a
README. See [`examples/README.md`](../../examples/README.md#where-the-logger-is-configured) for
which file configures which example.
