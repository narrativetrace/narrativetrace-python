<!-- source: documentation/choosing-an-integration.md blob 753ad8c19299 | translated: 2026-09-03 | reviewed: 2026-09-03 -->

# Eligiendo una integración

NarrativeTrace tiene un único modelo de captura — un evento de entrada/salida publicado a través de
la tubería — al que se llega mediante un pequeño número de mecanismos de conexión. Esta página
responde a "qué paquete necesito en realidad", primero como una tabla de referencia, luego como un
diagrama de decisión y, después, con las advertencias que tiene cada camino.

## Quieres... / Empieza con...

| Quieres | Empieza con |
|---|---|
| Trazas en las pruebas, con el mínimo cableado | `narrativetrace-pytest` (fixture `narrative_trace`) |
| Control explícito sobre qué se envuelve, en Python puro | `trace_object(obj, context)` — el núcleo, sin necesidad de framework |
| Ciclo de vida de peticiones en FastAPI/Starlette | `narrativetrace-asgi` |
| Propagar una traza a una llamada HTTP aguas abajo | `attach_traceparent` de `narrativetrace-asgi` (httpx) |
| Trazas en tu flujo de logs de producción | `LoggingTraceConsumer` / `NarrativeContextFilter` (núcleo) |
| Pipelines de structlog | `narrativetrace-structlog` |
| Spans de OpenTelemetry | `narrativetrace-otel` |
| Diagramas de secuencia a partir de un árbol de trazas capturado | `narrativetrace-diagrams` |
| Puerta de calidad de nombres en CI | script de consola `narrativetrace-clarity` |
| Flask (WSGI) o Django | Aún no publicado — consulta *Límites de la plataforma* más abajo |

Esta es la misma matriz que aparece en el [LEAME.md raíz](../../LEAME.md); también vive aquí como
ancla para el diagrama y los detalles que siguen.

## La decisión

Existe exactamente una primitiva de captura — `trace_object(obj, context)` — que envuelve de forma
directa y reflexiva cualquier objeto concreto de Python, en la instancia que le pases. No existe
ningún requisito de interfaz o clase base, como sí lo necesitaría una integración basada en un proxy
dinámico, así que la decisión gira en realidad en torno a *dónde* ocurre la envoltura, no a *si* un
objeto cumple los requisitos:

```text
¿Dónde quieres que empiecen las trazas?
   |
   +-- Dentro de mi suite de pruebas -----------> narrativetrace-pytest
   |                                              (fixture narrative_trace; sin envoltura manual)
   |
   +-- Alrededor de objetos concretos, en un
   |   script simple o código de aplicación ----> trace_object(obj, context) directamente (núcleo)
   |
   +-- A través del ciclo de vida de peticiones HTTP
   |     |
   |     +-- FastAPI / Starlette (ASGI) --------> narrativetrace-asgi
   |     +-- Flask / Django --------------------> aún no publicado (ver Límites de la plataforma)
   |
   +-- Junto a código que ya se ejecuta
       en varios hilos o tareas de asyncio -----> trace_object como antes, más una
                                                   instantánea de contexto en el límite
                                                   (ver Trabajo entre hilos y tareas más abajo)
```

No existe ningún mecanismo de conexión sin código a nivel de bytecode (no se incluye ningún import
hook ni auto-instrumentación mediante `sitecustomize.py`) — cada camino anterior es una llamada
explícita que hace tu código o un middleware que registras, nunca algo que reescribe las clases a
medida que se cargan.

## Algo que todos los caminos comparten

Todos los mecanismos anteriores construyen el mismo `TraceTree` a partir del mismo flujo de
`TraceEvent` — el `_TracedProxy` de `trace_object`, el fixture de pytest y el middleware de ASGI
terminan llamando todos al mismo contexto (`ContextVarNarrativeContext.capture_trace()`); ninguno
de ellos define su propia noción de una llamada capturada. Elegir una integración es una cuestión de
*cómo se envuelve la llamada*, nunca de qué se registra una vez envuelta — todos los caminos
convergen en la misma costura de captura por diseño, una decisión interna (PY-001, PY-004, PY-005)
que esta página no necesita volver a litigar.

## Advertencias por camino

- **`trace_object`** — envuelve la instancia que le pasas; una referencia al objeto *original*, sin
  envolver, evita la captura por completo, así que envuelve en el punto donde tu código entrega el
  objeto (una raíz de composición, un factory, un fixture), no después. Todo método público (sin
  guion bajo al inicio) se traza automáticamente; no hay una lista de habilitación por método más
  allá de los decoradores.
- **`narrativetrace-pytest`** — se autorregistra como plugin de pytest; el fixture `narrative_trace`
  ofrece un contexto por prueba, así que trazar algo que abarca varias pruebas (un recurso con
  alcance de sesión) necesita su propio contexto, construido a mano con `ContextVarNarrativeContext`.
- **ASGI (`narrativetrace-asgi`)** — solo se capturan los scopes HTTP (`scope["type"] == "http"`);
  los scopes de WebSocket y lifespan pasan sin modificarse. `excluded_paths` compara la ruta de la
  petición como cadena exacta, no como glob ni como prefijo — `/health` excluye solamente `/health`,
  nunca `/health/live`.
- **Trabajo entre hilos y tareas** — `ContextVarNarrativeContext` aísla los hilos *y* las tareas de
  asyncio por diseño (cada uno obtiene su propia vista). El trabajo enviado a un
  `ThreadPoolExecutor` o generado como una `asyncio.Task` solo se une a la traza padre mediante
  `ForkJoinGroup`/`FireAndForgetGroup` o una instantánea de contexto tomada en el límite — un hilo o
  tarea que nunca recibió una se mantiene aislado, y su llamada equivalente a `captureTrace()` solo
  ve su propio trabajo. Un problema conocido: hacer fork directamente dentro de un método trazado
  `async def` resuelve el padre a través de la pila de llamadas síncrona, que ahí está vacía, así que
  los hijos lanzados de esa manera aparecen como nuevas raíces en lugar de anidarse bajo el llamador
  `async` — haz fork desde un método síncrono, o desde un grupo de hilos, para conservar el
  anidamiento.
- **`narrativetrace-otel`** — requiere `opentelemetry-api>=1.20`; tiende un puente entre un
  `TraceTree` ya capturado y los spans de OTel (exportador por lotes), o bien escucha en vivo — no
  reemplaza la configuración propia del SDK/exportador de OpenTelemetry.

## Límites de la plataforma

Todos los caminos anteriores asumen CPython ≥ 3.12. El middleware de Flask (WSGI) y Django está
**planificado, pero aún no publicado** — el mismo contrato de límite de petición que
`narrativetrace-asgi` es la forma prevista, pero hoy no hay ningún paquete que instalar; consulta la
[Guía de funcionalidades](guia-de-funcionalidades.md) para conocer su estado. No se realizan pruebas
de compatibilidad con PyPy ni GraalPy.

## Recetas

Cada camino de la matriz tiene un ejemplo completo bajo [`examples/`](../../examples) (consulta
[`examples/README.md`](../../examples/README.md)) y una guía bajo [`guides/`](../guides) — esta
página responde *cuál*, esas otras responden *cómo*.
