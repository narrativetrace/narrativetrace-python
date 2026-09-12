# Logging & structlog

NarrativeTrace bridges to the stdlib `logging` framework and to `structlog`, emitting the *same*
canonical correlation keys from both.

## stdlib logging

Two pieces:

- `LoggingTraceConsumer` — an event consumer that logs enter/return at `DEBUG` and exceptions at
  `WARNING` (`!! {type}: {message} [{error_context}]`, control-sanitised).
- `NarrativeContextFilter` — a logging `Filter` that stamps the current scope's keys (`traceId`,
  `traceName`, `spanId`, `nt.class`, `nt.method`, `nt.depth`, service identity, request/user keys)
  onto every record.

```python
import logging
from narrativetrace import NarrativeContextFilter

handler = logging.StreamHandler()
handler.addFilter(NarrativeContextFilter())
logging.getLogger().addHandler(handler)
```

## One consumer per stream, many handlers

`nt.depth` is a private counter on each `LoggingTraceConsumer` instance *(since 0.1.2,
unreleased)*, so two of them replaying the *same* event stream (say, both attached as listeners on
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

*(since 0.1.2, unreleased)* — on PyPI's published `0.1.1`, replay `store.events()` through a
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

## Where this is wired in the examples

Every runnable example under `examples/` sends its trace to a realistically configured logger
alongside its console narration — `logging.basicConfig` in the composition root plus
`LoggingTraceConsumer`/`NarrativeContextFilter` from this guide, not a snippet copied into a
README. See [`examples/README.md`](../../examples/README.md#where-the-logger-is-configured) for
which file configures which example.
