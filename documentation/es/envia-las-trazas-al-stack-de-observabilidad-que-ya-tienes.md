<!-- source: documentation/recipes/send-traces-to-the-observability-stack-you-already-run.md blob b7d969c29603 | translated: 2026-10-18 | reviewed: - -->

# Envía las trazas al stack de observabilidad que ya tienes

## El problema

> Ya tenemos trazado y dashboards. No voy a adoptar un segundo sitio donde
> mirar — ¿puede esto entrar en el stack que ya ejecutamos?

Sí: una ejecución, dos consumidores. Las líneas de narrativa siguen yendo a tu
logger, y los mismos eventos se convierten en spans de OpenTelemetry al salir.
Abajo hay un checkout con ambas salidas lado a lado.

## Configuración mínima

`narrativetrace-otel` (su [línea de instalación está en la página de instalación](guia-de-instalacion.md))
más la API de OpenTelemetry, que el paquete deja de tu mano para que gane la
versión de tu SDK. Hay dos formas de entrar, y la diferencia es *cuándo* existe
un span:

| Modo | Clase | Úsalo cuando |
|---|---|---|
| En vivo, mientras se ejecutan los métodos | `OtelTraceEventListener` | Quieres spans en tu collector aunque el proceso muera a mitad de una petición — esta página |
| Por lotes, a posteriori | `TraceSpanExporter` | Quieres los spans de un árbol de traza terminado, exportados una sola vez, al menor coste de ejecución: `TraceSpanExporter(tracer).export(context.capture_trace().roots)` |

Cualquiera de los dos lo cableas tú, en tu propio código: el contexto recibe el
event store al que debe entregar los eventos, y un store que además entrega
cada evento a un consumidor es la forma en que un segundo consumidor se une al
primero ([guía de OpenTelemetry](guia-de-opentelemetry.md)). Abajo, un
exportador en memoria hace las veces de tu collector, que además es la imagen
más clara de lo que hace tu cableado real con uno real.

## El escenario

El store es la única idea nueva: entrega cada evento a la narración que ya
tienes y al listener de OpenTelemetry, y lo conserva para `capture_trace()`
como cualquier store. El checkout en sí se envuelve exactamente como en todas
las demás páginas:

```python
"""documentation/recipes/send-traces-to-the-observability-stack-you-already-run.md's scenario: ONE
run of the checkout writes the log lines it always wrote AND an OpenTelemetry span per traced call,
with the parentage and the attributes the page shows -- and without the redacted values (rule 8,
docs as tests).

A fixture, not a ``test_*`` module: ``recipe_artifacts.py`` runs it in its own pytest process so the
log file the page embeds holds this scenario alone. No ``narrative_trace`` fixture, deliberately:
this page's subject is the context a deployment composes -- the narration it already has and an
OpenTelemetry listener, fed from one event store -- and an in-memory exporter stands in for the
collector. The exported spans are written out by ``write_exported_spans``, naming and sorting
everything it prints, so one run's dump is byte-identical to the next: a raw span dump carries
timestamps and OpenTelemetry's own generated ids and could never be embedded.
"""

import os
from pathlib import Path

from narrativetrace_otel import OtelTraceEventListener
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from examples.recipes.checkout.env import ARTIFACTS_ENV
from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import (
    ContextVarNarrativeContext,
    LoggingTraceConsumer,
    TraceEvent,
    TraceId,
    trace_object,
)
from narrativetrace.pipeline.event_store import EventStore

# A fixed trace id, so the page's embedded artifacts name the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")
CARD_NUMBER = "4242424242424242"


# snippet:begin wiring
class NarratedAndExportedStore(EventStore):
    """Hands every event to the narration and to OpenTelemetry as it happens, and keeps it for
    ``capture_trace()`` -- the one place the two consumers meet."""

    def __init__(self, narration: LoggingTraceConsumer, export: OtelTraceEventListener) -> None:
        super().__init__()
        self._narration = narration
        self._export = export

    def add(self, event: TraceEvent) -> None:
        self._narration.accept(event)
        self._export(event)
        super().add(event)


# snippet:end wiring


def test_one_run_narrates_and_exports() -> None:
    spans = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(spans))
    store = NarratedAndExportedStore(
        LoggingTraceConsumer(), OtelTraceEventListener(provider.get_tracer("narrativetrace"))
    )
    context = ContextVarNarrativeContext(store=store)
    context.adopt_trace_id(DEMO_TRACE_ID)
    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()
    inventory = trace_object(stock, context)
    payments = trace_object(PaymentService(), context)
    orders = trace_object(repository, context)
    checkout = trace_object(OrderService(inventory, payments, orders), context)

    order_id = checkout.place_order("C-1234", "SKU-KB", 2, CARD_NUMBER)

    exported = spans.get_finished_spans()
    assert order_id == "ORD-C-1234-SKU-KB-2"
    assert_one_span_per_traced_call(exported)
    assert_no_redacted_value_was_exported(exported)
    assert_parameters_are_typed(exported)
    write_exported_spans(exported)
    provider.shutdown()


def assert_one_span_per_traced_call(exported: tuple[ReadableSpan, ...]) -> None:
    """Four traced calls, four spans, ended innermost first -- and the tree is reconstructed."""
    assert [span.name for span in exported] == [
        "InventoryService.reserve",
        "PaymentService.charge",
        "OrderRepository.save",
        "OrderService.place_order",
    ]
    by_id = {span_id(span): span for span in exported}
    root = named(exported, "OrderService.place_order")
    charge = named(exported, "PaymentService.charge")
    assert charge.parent is not None
    assert by_id[charge.parent.span_id] is root
    assert root.parent is None


def assert_no_redacted_value_was_exported(exported: tuple[ReadableSpan, ...]) -> None:
    """What the deny-list caught never reaches the exporter either -- there is no attribute for
    it, not even one holding the marker."""
    attributes = {
        key: str(value) for span in exported for key, value in (span.attributes or {}).items()
    }
    assert "narrative.param.card_number" not in attributes
    assert "narrative.param.card" not in attributes
    assert not any(CARD_NUMBER in value for value in attributes.values())


def assert_parameters_are_typed(exported: tuple[ReadableSpan, ...]) -> None:
    """``quantity: 2`` is an integer attribute, not the string ``"2"``."""
    root = named(exported, "OrderService.place_order")
    assert root.attributes is not None
    assert root.attributes["narrative.param.quantity"] == 2
    assert isinstance(root.attributes["narrative.param.quantity"], int)


def span_id(span: ReadableSpan) -> int:
    assert span.context is not None
    return int(span.context.span_id)


def named(exported: tuple[ReadableSpan, ...], name: str) -> ReadableSpan:
    return next(span for span in exported if span.name == name)


def write_exported_spans(exported: tuple[ReadableSpan, ...]) -> None:
    """The dump the page embeds: span name, parent, and every attribute, sorted by key."""
    names = {span_id(span): span.name for span in exported}
    lines: list[str] = []
    for span in exported:
        parent = names[span.parent.span_id] if span.parent else "(none — this is the root)"
        lines += [f"span: {span.name}", f"  parent: {parent}"]
        lines += [f"    {key}: {value}" for key, value in sorted((span.attributes or {}).items())]
    target = Path(os.environ[ARTIFACTS_ENV])
    target.mkdir(parents=True, exist_ok=True)
    (target / "exported-spans.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
```

## La salida real

**Las líneas de log**, sin cambios por nada de esto — la misma narración que
produce [Añade logging a este servicio](anade-registro-a-este-servicio.md):

```text
DEBUG [solid wand romps] [narrativetrace] - → OrderService.place_order(customer_id: "C-1234", sku: "SKU-KB", quantity: 2, card_number: [REDACTED])
DEBUG [solid wand romps] [narrativetrace] - → InventoryService.reserve(sku: "SKU-KB", quantity: 2)
DEBUG [solid wand romps] [narrativetrace] - ← returned: null
DEBUG [solid wand romps] [narrativetrace] - → PaymentService.charge(customer_id: "C-1234", amount_cents: 7998, card: [REDACTED])
DEBUG [solid wand romps] [narrativetrace] - ← returned: "PAY-C-1234-7998"
DEBUG [solid wand romps] [narrativetrace] - → OrderRepository.save(order: Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998))
DEBUG [solid wand romps] [narrativetrace] - ← returned: null
DEBUG [solid wand romps] [narrativetrace] - ← returned: "ORD-C-1234-SKU-KB-2"
```

**Los spans que salieron de la misma ejecución**, tal como los recibió el
exportador en memoria — nombre, padre y cada atributo, ordenados:

```text
span: InventoryService.reserve
  parent: OrderService.place_order
    narrative.class: InventoryService
    narrative.method: reserve
    narrative.outcome: null
    narrative.param.quantity: 2
    narrative.param.sku: SKU-KB
    narrative.trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
    narrative.trace_name: solid wand romps
    nt.chapterId: OrderService.place_order
    nt.entryType: entry
    nt.schemaVersion: 1.2
    nt.storyId: OrderService.place_order
span: PaymentService.charge
  parent: OrderService.place_order
    narrative.class: PaymentService
    narrative.method: charge
    narrative.outcome: "PAY-C-1234-7998"
    narrative.param.amount_cents: 7998
    narrative.param.customer_id: C-1234
    narrative.trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
    narrative.trace_name: solid wand romps
    nt.chapterId: OrderService.place_order
    nt.entryType: entry
    nt.schemaVersion: 1.2
    nt.storyId: OrderService.place_order
span: OrderRepository.save
  parent: OrderService.place_order
    narrative.class: OrderRepository
    narrative.method: save
    narrative.outcome: null
    narrative.param.order.amount_cents: 7998
    narrative.param.order.customer_id: C-1234
    narrative.param.order.order_id: ORD-C-1234-SKU-KB-2
    narrative.param.order.quantity: 2
    narrative.param.order.sku: SKU-KB
    narrative.trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
    narrative.trace_name: solid wand romps
    nt.chapterId: OrderService.place_order
    nt.entryType: entry
    nt.schemaVersion: 1.2
    nt.storyId: OrderService.place_order
span: OrderService.place_order
  parent: (none — this is the root)
    narrative.class: OrderService
    narrative.method: place_order
    narrative.outcome: "ORD-C-1234-SKU-KB-2"
    narrative.param.customer_id: C-1234
    narrative.param.quantity: 2
    narrative.param.sku: SKU-KB
    narrative.trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
    narrative.trace_name: solid wand romps
    nt.chapterId: OrderService.place_order
    nt.entryType: entry
    nt.schemaVersion: 1.2
    nt.storyId: OrderService.place_order
```

## Cómo leerlo

- **Cuatro llamadas trazadas, cuatro spans, un árbol.** Los spans llegan en el
  orden en que *terminaron* — el más interno primero, la raíz la última, que es
  como cualquier pipeline OTel ve un árbol terminado. La filiación no se
  infiere de ese orden ni de un contexto ambiente: el listener lee el
  `parent_span_id` explícito de cada evento, por eso `InventoryService.reserve`,
  `PaymentService.charge` y `OrderRepository.save` nombran todos a
  `OrderService.place_order` como su padre aunque terminaran antes que él.
- **Qué lleva cada span.** `narrative.class` y `narrative.method` son la
  llamada; `narrative.param.<name>` es un atributo por parámetro, con tipo
  (`narrative.param.quantity: 2` es un entero, no la cadena `"2"` — el fixture
  lo afirma); `narrative.outcome` es el valor devuelto tal como lo renderiza la
  narración, así que un método que devolvió `None` lleva
  `narrative.outcome: null`. `narrative.trace_id` y `narrative.trace_name` son
  la identidad propia de NarrativeTrace para la traza, llevada como atributos
  para que un span en tu backend pueda emparejarse con la línea de log y el
  fichero de traza que describen la misma llamada —
  [Sigue una petición entre servicios](sigue-una-peticion-entre-servicios.md)
  es el mismo id haciendo el mismo trabajo a través de la frontera de un
  proceso. Los atributos `nt.*` marcan el esquema que siguen estos atributos y
  la historia a la que pertenece la llamada.
- **Un parámetro dataclass llega aplanado.** `OrderRepository.save(order)` es
  un parámetro, y se exportó como `narrative.param.order.order_id`,
  `narrative.param.order.customer_id`, `narrative.param.order.sku`,
  `narrative.param.order.quantity`, `narrative.param.order.amount_cents` —
  campo a campo, porque así se renderizó el valor: leyendo su estado, nunca
  llamando a su `__str__`.
- **La ocultación también alcanza este camino.** No hay ningún atributo
  `narrative.param.card_number` ni `narrative.param.card` en ningún span de
  arriba — ni un atributo que contenga `[REDACTED]`, ningún atributo en
  absoluto. Un valor denegado se descarta en la captura, antes de que exista el
  evento, así que ningún consumidor puede recibirlo; el fixture lo afirma además
  del árbol de spans
  ([Mantén los secretos fuera de los logs](manten-los-secretos-fuera-de-los-logs.md)).
- **Qué ajuste movió qué evento a qué consumidor.** Tres decisiones, en este
  orden:
  1. El nivel de trazado decide si se crea un evento siquiera. En `SUMMARY`
     estos mismos cuatro spans se exportan *sin* los atributos
     `narrative.param.*`, porque a ese nivel los valores de los parámetros no
     se renderizan; en `OFF` no hay evento, y por tanto no hay span — ambas
     cosas se afirman en las pruebas de recetas de este repositorio
     ([Traza en producción sin el coste](traza-en-produccion-sin-el-coste.md)).
  2. El store decide quién ve el evento. Aquí un store entrega cada evento a la
     narración, luego a la exportación, y luego lo conserva; la retención — lo
     que leen `capture_trace()` y los ficheros de traza — no se toca. No se le
     quitó nada al logger para alimentar al exportador.
  3. El nivel de tu logger decide qué se *imprime*. Subir el logger
     `narrativetrace` a `INFO` vacía el bloque de log de arriba y no cambia
     nada de los spans.
- **Por qué esto no es un segundo sitio donde mirar.** Los spans son tuyos, en
  tu collector, bajo el nombre de tu servicio, junto a los spans que tu
  framework ya emite. Lo que NarrativeTrace añade es un span por *llamada a
  método trazada*, con los parámetros y el resultado en él — un nivel por debajo
  del span HTTP que ya tienes.

## Qué no se captura

- **Lo que tu stack hace con los spans es cosa de tu stack.** El muestreo, la
  retención, la indexación y si un atributo se puede buscar son decisiones del
  collector y del backend. Esta página muestra lo que sale del proceso; no se
  afirma nada sobre la UI de ningún proveedor.
- **Los ids no se comparten.** OpenTelemetry genera sus propios ids de traza y
  de span para los spans que crea aquí, y la identidad de NarrativeTrace viaja
  como atributos `narrative.trace_id` / `narrative.trace_name`. La posición de
  un span en la cascada de tu backend es de OTel; emparejarlo con una línea de
  log es trabajo del atributo.
- **En vivo y por lotes no son los mismos spans.** El listener de esta página
  crea un span mientras se ejecuta un método, de modo que un huérfano (una
  entrada sin salida — un proceso matado a mitad de llamada) acaba terminado con
  estado de error por el propio mapa acotado del listener. El exportador por
  lotes solo ve árboles terminados y añade `narrative.duration_ms`, que el
  camino en vivo no tiene.
- **El coste es un listener en el hilo de quien llama.** El store ejecuta
  ambos consumidores en línea, así que la creación de spans está en el camino
  de la llamada trazada. Ese es el precio de ver el span mientras el método aún
  se ejecuta; un consumidor con búfer lo saca del hilo de quien llama a cambio
  de descartar eventos bajo presión, con cada pérdida contada ([README, Concurrency](../../README.md#concurrency)).
- **Solo se exporta lo que se traza.** No existe ningún span para una llamada
  que ninguna integración interceptó — el camino de exportación hereda
  exactamente el límite del camino de captura.

**La skill para esto:** `narrativetrace-doctor` — una comprobación de cableado
por integración de framework, e informa de si algún sink recibe de verdad lo
que se traza.
