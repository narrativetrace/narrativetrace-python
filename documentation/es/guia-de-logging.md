<!-- source: documentation/guides/logging.md blob 8e11e0235925 | translated: 2026-09-17 | reviewed: - -->

# Logging, structlog y Loguru

NarrativeTrace se conecta con el framework `logging` de la stdlib y con `structlog`, emitiendo las
*mismas* claves de correlación canónicas desde ambos. Un usuario de Loguru llega a la misma traza
a través de la interoperabilidad con la stdlib que el propio Loguru ya documenta — consulta
[Loguru](#loguru) más abajo.

## logging de la stdlib

Dos piezas:

- `LoggingTraceConsumer` — un consumidor de eventos que registra la entrada y el retorno en nivel
  `DEBUG`, y las excepciones en nivel `WARNING` (`!! {type}: {message} [{error_context}]`, con los
  caracteres de control depurados).
- `NarrativeContextFilter` — un `Filter` de logging que estampa las claves del ámbito actual
  (`traceId`, `traceName`, `spanId`, `nt.class`, `nt.method`, `nt.depth`, identidad del servicio,
  claves de petición/usuario) en cada registro. `traceName` y `runName` *(since 0.1.2)* están siempre presentes una vez que el filtro ha tocado un registro — `""` cuando
  no hay ninguna traza ni ejecución activa — así que un patrón que referencia cualquiera de las
  dos nunca lanza una excepción en una línea sin traza.

```python
import logging
from narrativetrace import NarrativeContextFilter

handler = logging.StreamHandler()
handler.addFilter(NarrativeContextFilter())
logging.getLogger().addHandler(handler)
```

## Un consumidor por flujo, muchos handlers

`nt.depth` es un contador privado de cada instancia de `LoggingTraceConsumer` *(since 0.1.2)*, así que dos de
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

*(since 0.1.2)* — en la versión publicada en PyPI, `0.1.1`, reproduce
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

## La ejecución tiene su propia clave MDC: `runName`

*(since 0.1.2)* El hook `pytest_sessionstart` de `narrativetrace-pytest` genera un id
de ejecución por sesión de pytest — nunca re-derivado — y llama a `set_run_name(run.name)` para
que `runName` (la frase propia de tres palabras de la ejecución, distinta de la `traceName` de
cualquier traza) viaje en cada línea de log durante toda la sesión, del mismo modo que
`request_log_scope` viaja por debajo de un ámbito de método; el hook `pytest_sessionfinish`
correspondiente la limpia de nuevo. Un patrón que muestra ambas claves:

```python
import logging

logging.basicConfig(format="%(asctime)s [%(traceName)s] [%(runName)s] %(message)s")
```

`runName` es `""` fuera de una sesión de pytest rastreada — un script sencillo, o
`export_to_logger` llamado desde uno — así que el mismo patrón es seguro en todas partes. Consulta
[Guía de configuración, § La ejecución tiene un
nombre](guia-de-configuracion.md#la-ejecución-tiene-un-nombre) para ver dónde más aparece el
nombre de la ejecución (el pie de página de la suite, `manifest.json`, el frontmatter de todo
documento Markdown de traza) y su invariante: nunca llega al artefacto estructural `.nt`.

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

## Loguru

NarrativeTrace no incluye ningún puente específico para Loguru — Loguru es un logger, no una
fuente de narración, y el puente con la stdlib de arriba es todo el mecanismo que necesita un
usuario de Loguru. Loguru documenta su propia interoperabilidad con la `logging` de la stdlib: un
`InterceptHandler` que hereda de `logging.Handler` y vuelve a registrar cada registro de la stdlib
a través de `logger` (consulta la propia receta de Loguru, ["Entirely compatible with standard
logging"](https://loguru.readthedocs.io/en/stable/overview.html)). Apunta el logger raíz de la
stdlib a ese handler, y `export_to_logger` — la misma reproducción de una sola llamada del [paso
"Envíala a tu logger" del tutorial de 60
segundos](sesenta-segundos.md#envíala-a-tu-logger) — llega a tu sink de Loguru sin ningún
código específico de NarrativeTrace:

```python
# main.py
import inspect  # nuevo: el recorrido de frames propio de InterceptHandler, tal cual la receta de Loguru
import logging  # nuevo: el logger de la stdlib del que hereda InterceptHandler; destino de export_to_logger
import sys  # nuevo: destino stdout para el sink de abajo

from loguru import logger  # nuevo: el sink de destino

from narrativetrace import (
    ContextVarNarrativeContext,
    IndentedTextRenderer,
    TraceId,
    export_to_logger,  # nuevo: reproduce una traza ya capturada en tu logger, en una llamada
    trace_object,
)


class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


# Un id de traza fijo, adoptado para que la salida incrustada de esta página siempre nombre la
# misma traza. Una ejecución real genera uno aleatorio cada vez (nunca este — es la constante
# propia de esta DEMO, no el valor por defecto de la librería) mediante el mismo
# TraceId.adopt_trace_id que usa una frontera al estilo servlet para una cabecera de traza entrante.
DEMO_TRACE_ID = TraceId("a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4")


# nuevo: la receta de interoperabilidad con la stdlib que el propio Loguru documenta, tal cual --
# consulta https://loguru.readthedocs.io/en/stable/overview.html, "Entirely compatible with
# standard logging". NarrativeTrace no incluye ningún puente propio para Loguru; esta receta es
# todo el mecanismo -- cada registro que emite un logger de la stdlib (incluidos los de
# export_to_logger) se vuelve a registrar a través de `logger`.
class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Obtiene el nivel de Loguru correspondiente, si existe.
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Busca quién llamó, a partir de dónde se originó el mensaje registrado.
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# nuevo: un sink fijo, sin timestamp, para que la salida incrustada de esta página nunca varíe
# según el reloj -- tu propio sink conserva su formato, colores y rotación reales; solo esta demo
# necesita determinismo.
logger.remove()
logger.add(sys.stdout, format="{level} | {message}", colorize=False)
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

context = ContextVarNarrativeContext()
context.adopt_trace_id(DEMO_TRACE_ID)
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

trace = context.capture_trace()  # nuevo: se captura una vez, reutilizada por print y export
print(IndentedTextRenderer().render(trace))

export_to_logger(trace)  # nuevo: el mismo export de una llamada del paso anterior -- ahora en Loguru
```

```bash
uv run main.py
```

```text
trace: loose hook parks (a1b2c3d)

OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3) → "ORD-cust-1-prod-42-3" — 0ms
DEBUG | → OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3)
DEBUG | ← returned: "ORD-cust-1-prod-42-3"
```

(el formato `"{level} | {message}"` del sink de esta demo es una elección de esta página, para una
salida que nunca varía según el reloj; tu sink real conserva el formato, los colores y la rotación
que ya tengas configurados.) Un usuario de Loguru conserva todo lo que Loguru ya le da — sinks,
rotación, colores, `logger.catch` — completamente intacto; `export_to_logger` solo reproduce una
traza ya capturada a través del puente con la stdlib que el `InterceptHandler` de Loguru ya está
escuchando. Lo que deja de escribir es la llamada a `logger.info(...)` (o `logger.debug(...)`)
dentro del propio método de negocio — las dos líneas de arriba vienen del nombre de
`place_order`, los nombres de sus parámetros y su valor de retorno, la información que el código
ya tenía, no de una llamada que alguien escribió.

## Dónde está conectado esto en los ejemplos

Todo ejemplo ejecutable bajo `examples/` envía su traza a un logger configurado de forma realista,
junto a su narración de consola — `logging.basicConfig` en la raíz de composición más
`LoggingTraceConsumer`/`NarrativeContextFilter` de esta guía, no un fragmento copiado en un README.
Consulta [`examples/README.md`](../../examples/README.md#where-the-logger-is-configured) para ver
qué archivo configura cada ejemplo.
