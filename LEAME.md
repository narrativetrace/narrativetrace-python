<!-- source: README.md blob d471648a833c | translated: 2026-09-07 | reviewed: - -->

# NarrativeTrace (Python)

[English](README.md) | **Español** | [Português](LEIAME.md) | [简体中文](自述文件.md)

> El código es el log.

NarrativeTrace convierte el código Python en ejecución en una narrativa legible, construida a
partir de los nombres de método, clase y parámetro que ya escribiste. Sin líneas `logger.info(...)`.
Si la traza es ilegible, tu código necesita mejores nombres — no más sentencias de log.

Con prisa: [pruébalo localmente](#pruébalo-localmente) → [añádelo a una sola
prueba](#añádelo-a-una-sola-prueba) → [elige tu integración](#elige-tu-integración).

## El problema

La mitad de este método es ruido de logging:

```python
def place_order(self, customer_id, product_id, quantity):
    logger.info("Placing order for customer %s product %s qty %s", customer_id, product_id, quantity)
    inventory = self.inventory.reserve(product_id, quantity)
    logger.debug("Reserved inventory: %s", inventory)
    payment = self.payments.charge(customer_id, inventory.total)
    logger.info("Payment processed: %s", payment.transaction_id)
    return OrderResult(payment.transaction_id, inventory.items)
```

La lógica de negocio son tres líneas; el logging son cuatro. Cada desarrollador escribe esos logs
de forma distinta — mensajes distintos, niveles distintos, valores incluidos distintos. El
resultado es inconsistente, verboso y enredado con el código que describe.

NarrativeTrace elimina esto por completo:

```python
def place_order(self, customer_id, product_id, quantity):
    inventory = self.inventory.reserve(product_id, quantity)
    payment = self.payments.charge(customer_id, inventory.total)
    return OrderResult(payment.transaction_id, inventory.items)
```

Lógica de negocio pura. La traza se genera a partir de los nombres de los métodos, los nombres de
los parámetros y los valores de retorno — la información que ya estaba ahí.

## Cómo se ve la salida

Envuelve los colaboradores una vez y ejecuta el código; esta es la salida real de un flujo de
pedido con tres servicios (`OrderService` llamando a un `InventoryService` y a un `PaymentService`,
ambos también envueltos):

```
OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3)
├── InventoryService.reserve(product_id: "prod-42", quantity: 3) → "reserved 3 of prod-42" — 0ms
├── PaymentService.charge(customer_id: "cust-1", amount: 30) → "txn-cust-1-30" — 0ms
└── → "order placed: txn-cust-1-30" — 0ms
```

**Cuando algo sale mal**, la traza hace visible el bug:

```
OrderService.place_order(customer_id: "cust-broke", product_id: "prod-7", quantity: 3)
├── InventoryService.reserve(product_id: "prod-7", quantity: 3) → "reserved 3 of prod-7" — 0ms
├── PaymentService.charge(customer_id: "cust-broke", amount: 30) !! PaymentDeclinedError: payment declined for customer cust-broke — 0ms
└── !! PaymentDeclinedError: payment declined for customer cust-broke — 1ms
```

`InventoryService.reserve` fue llamado pero `InventoryService.release` no aparece en ninguna parte
de la traza — el bug está a la vista sin necesidad de un depurador.

**La traza vale tanto como tus nombres.** El mismo flujo «el jugador se une al mundo» de
[`examples/minecraft`](examples/minecraft), trazado dos veces — una con nombres de dominio, otra
con nombres genéricos, ambas ejecuciones reales:

```
→ WorldServer.player_joined(player_name: "Steve")
  → WorldGenerator.generate_chunk(x: 0, z: 0)
  ← WorldGenerator.generate_chunk → Chunk(x=0, z=0, biome="plains")
  → PlayerInventory.add_item(item: Item.OAK_LOG, quantity: 4)
  ← PlayerInventory.add_item → True
  → CraftingTable.craft(recipe: Recipe.WOODEN_PICKAXE)
  ← CraftingTable.craft → Item.WOODEN_PICKAXE
  → CreatureSpawner.spawn_hostile(type: CreatureType.ZOMBIE, x: 10, y: 64, z: 20)
  ← CreatureSpawner.spawn_hostile → Creature(type=CreatureType.ZOMBIE, x=10, y=64, z=20)
← WorldServer.player_joined → "Steve joined the world"
```

```
→ GameManager.handle(input: "Steve")
  → DataProcessor.process(a: 0, b: 0)
  ← DataProcessor.process → DataResult(a=0, b=0, tag="plains")
  → StateManager.update(type: 1, count: 4)
  ← StateManager.update → True
  → ThingFactory.create(type: 1)
  ← ThingFactory.create → 1
  → EntityHandler.execute(kind: 1, a: 10, b: 64, c: 20)
  ← EntityHandler.execute → Entity(kind=1, a=10, b=64, c=20)
← GameManager.handle → "Steve joined the world"
```

Mismo grafo de llamadas, mismos valores de retorno, solo cambian los nombres — `narrativetrace-clarity`
pone un número a la diferencia (0.72 frente a 0.53 en las dos ejecuciones de arriba). Si tu código
no puede contar su propia historia, necesita refactorización, y por eso NarrativeTrace también
[puntúa tus nombres](documentation/es/guia-de-claridad.md).

### Por qué esto importa para el desarrollo asistido por IA

Cada línea `logger.info(...)` es una línea que las herramientas de IA para programar tienen que
parsear, gastar tokens en ella y sortear al razonar. Elimínalas y el mismo presupuesto de tokens
cubre más de tu código real, el modelo ve lo que hace el código en lugar de cómo lo registra en el
log, y los pull requests muestran cambios de lógica de negocio en vez de cambios mezclados de
lógica y logging.

### Cómo se compara

A diferencia de un árbol de spans de OpenTelemetry (construido para máquinas y paneles), una
NarrativeTrace se lee como prosa para humanos y LLM. Ambos se combinan: `narrativetrace-otel` emite
la misma traza como spans de OTel tipados, así que obtienes la narrativa humana *y* la correlación
del backend a partir de una sola captura.

### No reemplaza tu stack de logging

NarrativeTrace no es un framework de logging. No aporta handler, ni formatter, ni pipeline de
envío — tu configuración de `logging` (handlers, formatters, `dictConfig`/`fileConfig`) o tu
cadena de procesadores de structlog sigue funcionando exactamente como hoy.

Lo que reemplaza son las sentencias de narración escritas a mano — las líneas
`logger.info("Placing order %s for customer %s", ...)` de [el problema](#el-problema) más arriba.
Un método trazado produce esa misma narrativa automáticamente, a partir de los valores reales de
parámetros y retorno en la llamada, sin código de narración en el cuerpo del método. Esa
narrativa se captura por su propio camino — no interceptando ni reconfigurando tu pipeline de
logging.

Dos puentes opcionales permiten que esa narrativa — o solo su identidad — viaje por tu stack
existente, sin modificarlo:

- **`LoggingTraceConsumer`** envía las líneas generadas de entrada/retorno/excepción a través de
  `logging.getLogger("narrativetrace").log(...)` — la misma llamada que haría una sentencia
  escrita a mano, así que cada handler y formatter que ya tienes sigue recibiéndolas, intactos.
- **`narrativetrace-structlog`** no genera líneas en absoluto: su procesador estampa las mismas
  claves de correlación (`traceId`, `spanId`, `nt.class`, `nt.method`, …) en cada diccionario de
  evento que ya fluye por tu cadena de procesadores, incluidas las que escribiste a mano.
  `NarrativeContextFilter` hace el equivalente para `logging` estándar, como un `Filter` en tu
  propio handler.

Una sentencia `logger.info(...)` escrita a mano junto a una llamada trazada se mezcla libremente
— mismo logger, mismo stream, mismos handlers. NarrativeTrace solo añade a lo que ya existe.

## Pruébalo localmente

Sin proyecto, sin cableado — desde un clon de este repositorio, ejecuta en vivo el ejemplo insignia:

```bash
./demo.sh --list                                   # ecommerce, hotel_booking, minecraft, library
./demo.sh --example ecommerce --no-pause           # el ejemplo insignia: fork-join, ocultación, fallos
./demo.sh --example ecommerce --classic            # la misma ejecución como logs clásicos con marca de tiempo
./demo.sh --example ecommerce --lang es            # la misma traza, narrada en español (también zh-CN)
```

`./demo.sh` instala el workspace en su primera ejecución (`uv sync --all-packages`, lockfile
congelado) y es silencioso en cada ejecución posterior — sin un paso de configuración aparte.

Sin `--no-pause` la demo se detiene tras cada escenario — `[Enter]` continúa, `q` sale — y cada
escenario se abre con una nota sobre cómo está cableada *esa* traza. Un fragmento de la salida real:

```
→ OrderService.place_order(customer_id: "C-1234", product_id: "SKU-MECHANICAL-KB", quantity: 2)
  → CustomerService.find_customer(customer_id: "C-1234")
  ← CustomerService.find_customer → Customer(id="C-1234", name="Alice Johnson", tier=CustomerTier.GOLD)
⑂ fork group created [groupId: fork-1]
→ DiscountService.calculate_discount(customer_id: "C-1234", product_id: "SKU-MECHANICAL-KB")
← DiscountService.calculate_discount → Discount(percent=10)
⑃ fork joined [groupId: fork-1, members: 2]
  → PaymentService.charge(customer_id: "C-1234", amount: 166.97, card_token: [REDACTED])
  ← PaymentService.charge → PaymentConfirmation(transaction_id="TXN-00001", amount=166.97)
```

Fuera de este repositorio, lo mismo no requiere ningún proyecto en absoluto — instala y ejecuta:

```bash
uv add narrativetrace
```

La publicación en PyPI todavía no está hecha — hasta que los paquetes estén en el índice, trabaja
desde una copia de este repositorio (`uv sync --all-packages`).

La publicación en PyPI todavía no está hecha — hasta que los paquetes estén en el índice, trabaja
desde una copia de este repositorio (`uv sync --all-packages`).

```python
from narrativetrace import ContextVarNarrativeContext, MarkdownRenderer, trace_object

context = ContextVarNarrativeContext()
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

print(MarkdownRenderer().render(context.capture_trace()))
```

Consulta [examples/README.md](examples/README.md) para ver qué enseña cada uno de los cuatro
ejemplos de la demo, y el ejemplo [`fastapi_service`](examples/fastapi_service) para la porción de
ASGI (no está en el lanzador de la demo — necesita un servidor en ejecución).

## Añádelo a una sola prueba

El camino más corto desde «librería interesante» hasta «vi una traza útil de mi propio código» es
el plugin de pytest. Python ≥ 3.12.

**1. Instálalo** — trae consigo el núcleo, los renderizadores de diagramas y el motor de claridad:

```bash
uv add --dev narrativetrace-pytest
```

**2. Traza un servicio en una prueba** — el plugin se registra solo; basta con pedir el fixture:

```python
from narrativetrace import trace_object

class TestOrderService:
    def test_customer_places_order(self, narrative_trace):
        service = trace_object(OrderService(), narrative_trace)
        service.place_order("C-1234", "SKU-KB", 2)
```

**3. Activa la salida de artefactos y ejecuta la suite:**

```bash
NARRATIVETRACE_OUTPUT=1 uv run pytest
```

**4. Abre la narrativa** — la clase de prueba se convirtió en el directorio, el método de prueba se
convirtió en el archivo:

```text
narrative-traces/traces/TestOrderService/test_customer_places_order.md
```

Esta es la salida real, ejecutada de verdad, de esa prueba exacta:

```markdown
---
type: trace
scenario: Test customer places order
entry_point: OrderService.place_order
duration_ms: 0
trace_id: aa4ae2eaa56e7e49b7aa42aece5999f0
trace_name: muted stone tests
method_count: 1
error_count: 0
---

## Trace: OrderService.place_order

**Scenario:** Test customer places order
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **OrderService.place_order**(customer_id: `"C-1234"`, product_id: `"SKU-KB"`, quantity: `2`) → `"ORD-C-1234-SKU-KB-2"` — 0ms
```

Cada prueba escribe su propio conjunto de artefactos — un `.json` complementario y
`diagrams/<Clase>/<slug>.mmd` para el formato `markdown` por defecto, además de un
`clarity-report.md` para toda la suite:

```text
narrative-traces/
├── traces/<ClaseDePrueba>/<slug>.md         la narrativa para humanos
├── traces/<ClaseDePrueba>/<slug>.json       la misma traza como JSON canónico
├── diagrams/<ClaseDePrueba>/<slug>.mmd      diagrama de secuencia Mermaid
├── clarity-results.json                 puntuaciones de nombres, una entrada por prueba
└── clarity-report.md                    feedback de nombres para toda la suite
```

¿Quieres seguir? Renombra el método y mira caer la puntuación de claridad, añade `@not_traced` y
observa un valor oculto → [Primeros 10 minutos](documentation/es/primeros-10-minutos.md) recorre
ambos con salida real.

## Elige tu integración

Las pruebas son donde empieza la mayoría. Esto es a dónde ir después:

| Lo que quieres | Empieza con |
|---|---|
| Trazas en las pruebas, con el mínimo cableado | `narrativetrace-pytest` (fixture `narrative_trace`) |
| Control explícito sobre qué se envuelve, en Python puro | `trace_object(obj, context)` — el núcleo, sin necesidad de framework |
| Ciclo de vida de peticiones de FastAPI/Starlette | `narrativetrace-asgi` |
| Propagar una traza a una llamada HTTP downstream | `attach_traceparent` de `narrativetrace-asgi` (httpx) |
| Trazas en tu flujo de logs de producción | `LoggingTraceConsumer` / `NarrativeContextFilter` (núcleo) |
| Pipelines de structlog | `narrativetrace-structlog` |
| Spans de OpenTelemetry | `narrativetrace-otel` |
| Diagramas de secuencia | `narrativetrace-diagrams` |
| Puerta de CI para la calidad de los nombres | script de consola `narrativetrace-clarity` |
| Flask (WSGI) o Django | Aún no disponible — consulta [Eligiendo una integración](documentation/es/eligiendo-una-integracion.md) |

Aquí no hay mecanismo de adjunción de cero código a nivel de bytecode — cada camino de arriba es
una llamada explícita a `trace_object(...)` o un middleware que registras tú mismo; nada reescribe
tus clases al cargarlas. Todo el detalle, un diagrama de decisión, y qué ocurre cuando
NarrativeTrace se apila con otros wrappers: [Eligiendo una
integración](documentation/es/eligiendo-una-integracion.md).

### Paquetes

| Paquete | Propósito |
|---|---|
| [`narrativetrace`](packages/narrativetrace) | Núcleo sin dependencias: captura, decoradores, renderizado, ocultación, concurrencia, exportación JSON, puente de logging |
| [`narrativetrace-pytest`](packages/narrativetrace-pytest) | Plugin de pytest: fixture `narrative_trace` por prueba, artefactos, pie de claridad |
| [`narrativetrace-diagrams`](packages/narrativetrace-diagrams) | Renderizadores de diagramas de secuencia Mermaid + PlantUML |
| [`narrativetrace-otel`](packages/narrativetrace-otel) | Puente de spans de OpenTelemetry (listener en vivo + exportador por lotes) |
| [`narrativetrace-asgi`](packages/narrativetrace-asgi) | Middleware ASGI (Starlette/FastAPI), traceparent W3C, accesor de la petición |
| [`narrativetrace-clarity`](packages/narrativetrace-clarity) | Motor de claridad de nombres + script de consola de puerta de CI |
| [`narrativetrace-structlog`](packages/narrativetrace-structlog) | Procesador de structlog que inyecta claves de correlación |
| [`narrativetrace-glossary`](packages/narrativetrace-glossary) | Glosario de dominio: el modelo `glossary.json`, lector/escritor determinista, vista en Markdown |

## Privacidad y seguridad

Esta librería se ejecuta dentro de tu proceso y escribe archivos que tu equipo va a compartir. Lo
que eso significa, en una sola pantalla:

| Superficie | ¿Se puede desactivar la ocultación integrada? |
|---|---|
| Plugin de pytest, middleware ASGI, puente de OTel, procesador de structlog, puente de logging de la stdlib | No |
| Un `ValueRenderer` personalizado que construye tu propio código | Sí — solo pasando `RedactionPolicy.DISABLED` explícitamente |
| `@not_traced` / `not_traced_field(...)` | No aplica — es lo que hace la ocultación, y siempre gana |

`@not_traced` en un parámetro o campo, y la lista de denegación basada en nombre (`password`,
`token`, `cvv`, `ssn`, …) más el enmascaramiento por forma de valor (cadenas con forma de
JWT/PAN/`Set-Cookie`, sin importar el nombre del campo), se aplican en todos los lugares donde un
valor se renderiza por reflexión — ninguna integración incluida expone una forma de sortearlos. Una
limitación conocida y documentada: una plantilla de narración `{param.path}` siempre comprueba la
lista de denegación por defecto, incluso cuando el renderizador circundante se construyó con una
política personalizada o desactivada — consulta [Privacidad y
ocultación](documentation/es/privacidad-y-ocultacion.md) para conocer el alcance exacto.

- **Un fallo del tracing no puede hacer fallar tu aplicación.** El registro está aislado frente a
  excepciones en todas las rutas; un `__str__` que lanza una excepción o un buffer lleno nunca
  cambian lo que tu método devuelve o lanza.
- **El uso de recursos está acotado.** La ruta de análisis con buffer es un anillo de tamaño fijo
  (65.536 eventos por defecto) que descarta en vez de bloquear bajo carga — y lo dice: una
  ejecución que perdió eventos imprime el recuento en su propio pie de suite en lugar de
  subreportar en silencio.
- **La introspección lee datos almacenados, no código.** Un getter `@property` calculado nunca se
  ejecuta; los únicos miembros que NarrativeTrace invoca son un `__str__` personalizado, un método
  `@narrative_summary`, y las rutas de propiedades nombradas en una plantilla
  `@narrated`/`@on_error` — mantenlos puros, como lo harías para un depurador.

→ [Privacidad y ocultación](documentation/es/privacidad-y-ocultacion.md) para el contrato fila por
fila verificado contra el código.

**Convivencia con otros wrappers.** Las librerías de contratos, los proxies DI/AOP y los agentes de
observabilidad (incluida la auto-instrumentación de OpenTelemetry) pueden envolver el mismo método
que envuelve NarrativeTrace. Esta implementación mantiene dos reglas para sus propios mecanismos: un solo
frame de traza por cruce de frontera de negocio — los métodos puente y las clases generadas por
contenedores nunca se narran — y ningún resultado depende de qué wrapper queda más afuera, así que
el resultado o la excepción de una llamada envuelta siempre llega a la traza, sin importar el orden
de apilado. `excluded_paths` de `narrativetrace-asgi` es el único mecanismo de exclusión disponible
hoy (por ruta, coincidencia exacta); `trace_object` no tiene nada que excluir por patrón, porque
envuelve una sola instancia que le pasas, no un barrido.

## Rendimiento

La captura está controlada por un nivel de tracing que se comprueba *antes* de que ocurra
cualquier renderizado (`NARRATIVETRACE_LEVEL`): ponlo en `OFF` y los wrappers cortocircuitan — sin
reflexión, sin trabajo de cadenas — antes de tocar tus argumentos. Para bucles calientes, reduce el
alcance trazado o baja el nivel en vez de trazarlo todo.

Todavía no hemos publicado cifras medidas de latencia/asignación para esta implementación como sí hace el
hermano Java — `uv run poe bench` (pytest-benchmark) está cableado en el toolchain, pero aún no se
ha escrito ninguna suite de benchmarks. Hasta que la haya, no asumas que las cifras de Java se
trasladan: los runtimes, y lo que cuesta en ellos cada línea de código de tracing, son distintos.
No vamos a afirmar «sobrecoste cero» en ningún sentido — trazar hace trabajo, y el trabajo cuesta
algo.

## Qué es gratuito y qué es Pro

**Gratis** es todo lo que hay en este repositorio — de código disponible bajo BSL 1.1, gratis en
producción, que pasa a Apache 2.0 cuatro años después de cada versión: el runtime completo, las
trazas por prueba en todos los formatos, la puntuación de claridad, el glosario de dominio, y todas
las integraciones de la tabla de arriba.

**Pro** es la inteligencia *entre* ejecuciones, construida sobre la misma captura: hoy eso es la
agregación de streams de eventos (`EventAggregator` — árboles agregados, puntos calientes, tasas de
error), publicada en una distribución comercial separada, nunca en este repositorio.
Resúmenes de flujo, diffs de migración, grafos de dependencias en tiempo de ejecución, y
manejadores de herramientas MCP para agentes de IA están planificados ahí a continuación. La [Guía
de funcionalidades](documentation/es/guia-de-funcionalidades.md) es la tabla de estado
autoritativa: etiqueta cada funcionalidad como Gratis, Pro, En desarrollo o Planificada, y cita el
código detrás de cada fila publicada.

## Concurrencia

Los grupos fork-join y fire-and-forget (lanzar y olvidar) propagan la identidad completa de la
traza a través de tareas de `asyncio` y pools de hilos, así que el trabajo concurrente se injerta
de vuelta bajo el span que lo lanzó con un id de grupo compartido — la historia se mantiene
coherente incluso cuando la ejecución no es secuencial. Un snapshot de contexto lleva la traza
*hacia dentro* de un worker y el trabajo trazado ahí *vuelve*: la pila que captura lo reporta desde
el momento en que se publica, de forma transitiva a través de una cadena de saltos async.

## Desarrollo

```bash
uv sync --all-packages
uv run poe check          # format-check + lint + typecheck + lint-imports + coverage + stress-quick + metrics + clarity + no-license-headers + translation-check + legal-check + bandit
```

## Documentación

Empieza aquí:

- [Primeros 10 minutos](documentation/es/primeros-10-minutos.md) — un servicio diminuto, salida real, desde la instalación hasta un valor ocultado
- [Eligiendo una integración](documentation/es/eligiendo-una-integracion.md) — qué paquete necesitas, como diagrama de decisión
- [Guía de instalación](documentation/es/guia-de-instalacion.md) — todos los paquetes, qué añade cada uno
- [Guía de configuración](documentation/es/guia-de-configuracion.md) — niveles de tracing, configuración de la salida, cadena de precedencia
- [Guía de decoradores](documentation/es/guia-de-decoradores.md) — `@narrated`, `@on_error`, `@not_traced`, el contrato de pureza

Para profundizar:

- [Privacidad y ocultación](documentation/es/privacidad-y-ocultacion.md) — el contrato de ocultación fila por fila, verificado contra el código
- [Qué commitear](documentation/es/que-commitear.md) — qué archivos generados son artefactos de CI, y cuáles (si los hay) son líneas base revisadas
- [Solución de problemas](documentation/es/solucion-de-problemas.md) — síntoma → causa → arreglo para los fallos que la gente realmente encuentra
- [Guía de pytest](documentation/es/guia-de-pytest.md) · [Guía de FastAPI/ASGI](documentation/es/guia-de-fastapi-asgi.md) · [Guía de OpenTelemetry](documentation/es/guia-de-opentelemetry.md) · [Guía de logging](documentation/es/guia-de-logging.md) · [Guía de claridad](documentation/es/guia-de-claridad.md)
- [Guía de funcionalidades](documentation/es/guia-de-funcionalidades.md) — cada funcionalidad que esta implementación publica, con nivel y estado
- [Referencia completa (`llms-full.md`)](documentation/llms-full.md) — todas las guías, en un solo archivo; [`llms.txt`](documentation/llms.txt) es el índice legible por máquina para agentes de IA

## Ejemplos y demo

Tutoriales ejecutables y probados viven bajo [`examples/`](examples) — consulta
[`examples/README.md`](examples/README.md) para el mapa: `ecommerce` (el ejemplo insignia:
decoradores, escenarios de fallo, fork-join y fire-and-forget con pool de hilos), `hotel_booking`
(puntuación de claridad a través de niveles de nombres), `minecraft` (refactorizado frente a sin
refactorizar, uno junto al otro), `library` (dataclasses que narran su propia historia), y
`fastapi_service` (la porción de ASGI).

## Licencia

La API y el formato de salida de NarrativeTrace son estándares abiertos (Apache 2.0). Su runtime es
gratuito y de código disponible (BSL 1.1, que pasa a Apache 2.0 cuatro años después de cada
versión). Pro es comercial.

Las distribuciones de este repositorio son ese runtime: **Business Source License 1.1** (SPDX
`BUSL-1.1`) — el texto completo está en [`LICENSE`](LICENSE). El uso en producción está concedido
para cualquier propósito, incluido el uso interno y los servicios que ofrezcas a tus propios
clientes; la única exclusión es ofrecer NarrativeTrace en sí —o un producto o servicio cuyo valor
derive sustancialmente de él— a terceros como un producto o servicio de logging, tracing o
narrativa de código. Cuatro años después de que se publique una versión, esa versión pasa a la
Apache License 2.0.

La prosa de la documentación es CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/); los
archivos de esquema JSON son Apache 2.0.

Ninguna de estas licencias otorga derechos de marca; NarrativeTrace es una marca comercial de
Empower Agile.

### La licencia, en palabras sencillas

Todo lo instalable desde este repositorio es Business Source License 1.1 hoy; los esquemas
JSON son Apache 2.0 (ver schema/README.md).

<!-- legal:plain-words:begin -->
**Gratis para ejecutar.** El runtime es de código disponible bajo la Business
Source License 1.1: puedes leerlo, auditarlo, modificarlo y usarlo en producción
sin coste — incluso dentro de los productos y servicios que vendes a tus propios
clientes.

**Una sola exclusión.** No puedes ofrecer NarrativeTrace en sí —o un producto o
servicio cuyo valor derive sustancialmente de él— a terceros como producto o
servicio de logging, tracing o narrativa de código.

**Se abre en una fecha.** Cada versión se convierte a Apache 2.0 cuatro años
después de publicarse; la fecha exacta se imprime en el LICENSE de esa versión.

*Este resumen es una cortesía, no una licencia. El archivo LICENSE es el único
texto vinculante; donde ambos difieran, prevalece el LICENSE.*
<!-- legal:plain-words:end -->
