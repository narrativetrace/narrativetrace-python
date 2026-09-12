<!-- source: documentation/guides/logging.md blob f101581900b6 | translated: 2026-09-12 | reviewed: - -->

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

## Un consumidor por flujo, muchos handlers

`nt.depth` es un contador privado de cada instancia de `LoggingTraceConsumer` *(since 0.1.2,
unreleased)*, así que dos de
ellas reproduciendo el *mismo* flujo de eventos (por ejemplo, ambas conectadas como listeners en
un mismo pipeline) reportan cada una su propia profundidad correcta — una ya no corrompe el
conteo de la otra. `NarrativeContextFilter` y el procesador de `structlog` no se ven afectados de
ninguna forma: leen la identidad compartida de clase/método/traza del frame más interno, que es
la misma para cualquier instancia que procese un evento, nunca el contador de profundidad propio
de un consumidor. Aun así, prefiere un solo `LoggingTraceConsumer` por flujo de eventos — es más
fácil de razonar, y una segunda instancia perdida es fácil de crear por accidente (por ejemplo,
dos piezas distintas de código de configuración creando cada una la suya). ¿Quieres la traza en
más de un lugar (stdout y un archivo, por ejemplo)? Añade más `logging.Handler` a su logger en
lugar de un segundo consumidor:

```python
logger = logging.getLogger("narrativetrace")
logger.addHandler(logging.StreamHandler())           # first destination
logger.addHandler(logging.FileHandler("trace.log"))  # second destination, same consumer
```

## `export_to_logger` — una sola llamada

*(since 0.1.2, unreleased)* — en la versión publicada en PyPI, `0.1.1`, reproduce
`store.events()` a través de un `LoggingTraceConsumer` a mano en su lugar.

`export_to_logger(trace, logger=None)` reproduce una traza ya capturada a través de un
`LoggingTraceConsumer` privado en una sola llamada — sin `EventStore` que conectar a mano, sin
bucle que escribir:

```python
from narrativetrace import ContextVarNarrativeContext, export_to_logger, trace_object

context = ContextVarNarrativeContext()
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

export_to_logger(context.capture_trace())
```

Cada llamada abre su propio consumidor privado, así que llamarla más de una vez — incluso de
forma concurrente, desde hilos distintos — nunca infringe la regla de "un consumidor por flujo"
de arriba.

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
