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
