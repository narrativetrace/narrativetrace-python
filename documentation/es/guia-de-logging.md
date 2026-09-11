<!-- source: documentation/guides/logging.md blob e987a2d7cfb1 | translated: 2026-09-11 | reviewed: - -->

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

## Dónde está conectado esto en los ejemplos

Todo ejemplo ejecutable bajo `examples/` envía su traza a un logger configurado de forma realista,
junto a su narración de consola — `logging.basicConfig` en la raíz de composición más
`LoggingTraceConsumer`/`NarrativeContextFilter` de esta guía, no un fragmento copiado en un README.
Consulta [`examples/README.md`](../../examples/README.md#where-the-logger-is-configured) para ver
qué archivo configura cada ejemplo.
