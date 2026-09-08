# narrativetrace-structlog

A [structlog](https://www.structlog.org) processor that injects [narrativetrace](../narrativetrace)
correlation keys (`traceId`, `traceName`, `spanId`, `nt.class`, HTTP/request keys, …) into every
event dict — the same canonical key set the stdlib `NarrativeContextFilter` stamps onto log
records, so both logging front-ends stay in lockstep.

```python
import structlog
from narrativetrace_structlog import narrative_context_processor

structlog.configure(processors=[narrative_context_processor, structlog.processors.JSONRenderer()])
```
