<!-- source: documentation/guides/logging.md blob 28814dbf375e | translated: 2026-09-03 | reviewed: 2026-09-03 -->

# Logging y structlog

NarrativeTrace se conecta con el framework `logging` de la stdlib y con `structlog`, emitiendo las
*mismas* claves de correlación canónicas desde ambos.

## logging de la stdlib

Dos piezas:

- `LoggingTraceConsumer` — un consumidor de eventos que registra la entrada y el retorno en nivel
  `DEBUG`, y las excepciones en nivel `WARNING` (`!! {type}: {message} [{error_context}]`, con los
  caracteres de control depurados).
- `NarrativeContextFilter` — un `Filter` de logging que estampa las claves del ámbito actual
  (`traceId`, `traceName`, `spanId`, `nt.class`, `nt.method`, `nt.depth`, identidad del servicio,
  claves de petición/usuario) en cada registro.

```python
import logging
from narrativetrace import NarrativeContextFilter

handler = logging.StreamHandler()
handler.addFilter(NarrativeContextFilter())
logging.getLogger().addHandler(handler)
```

## Ámbito a nivel de petición

Dentro de una petición HTTP, el middleware de ASGI abre un `request_log_scope(...)` para que las
claves de la petición (`httpMethod`, `httpRoute`, `clientIp`, identidad del usuario) viajen por
debajo de cualquier ámbito de método activo.

## structlog

`narrativetrace-structlog` proporciona un procesador que inyecta el mismo conjunto de claves:

```python
import structlog
from narrativetrace_structlog import narrative_context_processor

structlog.configure(
    processors=[narrative_context_processor, structlog.processors.JSONRenderer()]
)
```

Ambos frontends comparten `narrativetrace.current_scope_keys()` como única fuente de vocabulario,
por lo que sus conjuntos de claves nunca pueden desincronizarse.
