<!-- source: documentation/recipes/follow-a-flow-across-threads.md blob 37880c006918 | translated: 2026-10-18 | reviewed: - -->

# Sigue un flujo entre hilos

## El problema

> El checkout entrega las partes lentas a un pool de hilos. La traza se detiene
> en el submit y no puedo ver qué hizo el trabajo en segundo plano.

Un hilo no sabe nada de la traza en la que está otro hilo, así que entregar
trabajo a un pool entrega el trabajo y nada más. La traza también hay que
entregarla — de forma explícita, en el momento de enviar la tarea. Abajo hay una
ejecución que lo hace y otra que no.

## Configuración mínima

Nada más allá de la [instalación](guia-de-instalacion.md): `ForkJoinGroup` y
`FireAndForgetGroup` están en `narrativetrace`, junto al propio contexto. Cuál
usar depende de lo que haga después quien lanza:

| La llamada que lanza | El helper | El paso final |
|---|---|---|
| Espera al trabajo en segundo plano (esta página) | `ForkJoinGroup` | `merge()`, después de que terminen las tareas — injerta lo que registraron bajo el span que las lanzó |
| Retorna sin esperar | `FireAndForgetGroup` | Ninguno. Los hijos son un registro aparte, que se lee con `child_roots()` |

Para corrutinas, los mismos grupos aceptan `await group.run_async(lambda: …)` en
lugar de `wrap(...)`. La [sección Concurrency del README](../../README.md#concurrency)
es la versión corta de ambos.

Las líneas de log se escriben en el instante en que ocurre cada llamada (un
contexto cuyo store entrega cada evento a un `LoggingTraceConsumer`, el camino
en vivo de la [Guía de logging](guia-de-logging.md)), con el hilo y el id de
traza en bruto en el formato — en esta página la columna del hilo es la mitad
de la historia:

```python
THREADS_FORMAT = "%(levelname)-5s [%(threadName)s] [%(name)s] [%(traceId)s] - %(message)s"
```

Dos registros del log de esta página no tratan de una llamada — el fork y el
join — así que no llevan id de traza, y un formato que nombre `traceId` lanzaría
una excepción con ellos. Un filtro pequeño, que un proyecto que registra estas
líneas escribe una sola vez:

```python
class TraceIdOrBlank(logging.Filter):
    """The fork and join lines belong to no span, so they carry no ``traceId``: print a blank
    rather than let the format raise."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__.setdefault("traceId", "")
        return True


```

## El escenario

**El checkout, con los dos pasos lentos fuera de su propio hilo.** La entrega
es `group.wrap(...)` alrededor de cada tarea y `group.merge()` cuando ambas han
terminado:

```python
"""The checkout with the two slow steps off the caller's thread, for
documentation/recipes/follow-a-flow-across-threads.md."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Any

from examples.recipes.checkout.domain import Order, PaymentDeclinedError
from examples.recipes.checkout.fraud import RuleBasedFraudCheck
from examples.recipes.checkout.order_service import UNIT_PRICE_CENTS
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ForkJoinGroup, NarrativeContext


class ParallelCheckout:
    """Reserves the stock and runs the fraud check on an executor, waits for both, then charges
    and saves.

    A task handed to an executor runs on a thread that knows nothing about the caller's trace, so
    the trace has to be handed over with it: ``group.wrap`` takes a snapshot at submission time,
    the worker activates it, and ``group.merge()`` grafts what the worker recorded back under the
    span that launched it. Every forked task must be wrapped and ``merge()`` must run after they
    finish, or the children stay detached from the caller's trace.
    """

    def __init__(
        self,
        context: NarrativeContext,
        inventory: InventoryService,
        fraud: RuleBasedFraudCheck,
        payments: PaymentService,
        orders: OrderRepository,
        workers: ThreadPoolExecutor,
    ) -> None:
        self._context = context
        self._inventory = inventory
        self._fraud = fraud
        self._payments = payments
        self._orders = orders
        self._workers = workers

    def place_order(self, customer_id: str, sku: str, quantity: int, card_number: str) -> str:
        amount_cents = UNIT_PRICE_CENTS * quantity

        group = ForkJoinGroup.create(self._context)
        reserved = self._workers.submit(group.wrap(lambda: self._inventory.reserve(sku, quantity)))
        approved = self._workers.submit(
            group.wrap(lambda: self._fraud.approve(customer_id, amount_cents))
        )
        tasks: list[Future[Any]] = [reserved, approved]
        wait(tasks)  # the merge may only run after both are done
        group.merge()

        reserved.result()  # a task's own failure is the caller's, raised here
        if not approved.result():
            self._inventory.release(sku, quantity)
            raise PaymentDeclinedError("the fraud check refused the order")
        self._payments.charge(customer_id, amount_cents, card_number)
        order_id = f"ORD-{customer_id}-{sku}-{quantity}"
        self._orders.save(Order(order_id, customer_id, sku, quantity, amount_cents))
        return order_id
```

**La ejecución — y el mismo trabajo sin la entrega.** La segunda prueba envía
una llamada trazada al mismo pool sin grupo y sin wrap, que es el aspecto que
tenía el código antes de añadir la entrega:

```python
"""documentation/recipes/follow-a-flow-across-threads.md's scenario: the two tasks the checkout
hands to an executor stay inside the caller's trace when they are wrapped, and a task submitted
without the handover starts a trace of its own (rule 8, docs as tests).

A fixture, not a ``test_*`` module: ``recipe_artifacts.py`` runs the first test alone for the log
the page embeds (the second one's trace id is freshly generated on every run, which is the finding
it reports and the one thing no embedded block can hold) and the second test in a run of its own.
One worker thread, named: the page embeds a real run's log byte for byte, and two threads logging
at once interleave differently every time. The handover is identical either way.
"""

import logging
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from examples.recipes.checkout import correlation_logging
from examples.recipes.checkout.env import ARTIFACTS_ENV
from examples.recipes.checkout.fraud import RuleBasedFraudCheck
from examples.recipes.checkout.live_logging import LoggingEventStore
from examples.recipes.checkout.parallel_checkout import ParallelCheckout
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, TraceNode, trace_object
from narrativetrace.render import StructuralTraceRenderer

# A fixed trace id, so the page's embedded artifacts name the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")

correlation_logging.install(correlation_logging.THREADS_FORMAT)


@pytest.fixture
def context() -> ContextVarNarrativeContext:
    return ContextVarNarrativeContext(store=LoggingEventStore(logging.getLogger("narrativetrace")))


@pytest.fixture
def workers() -> Iterator[ThreadPoolExecutor]:
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="checkout-worker")
    yield pool
    pool.shutdown(wait=True)


def test_the_background_tasks_stay_in_the_customers_trace(
    context: ContextVarNarrativeContext, workers: ThreadPoolExecutor
) -> None:
    context.adopt_trace_id(DEMO_TRACE_ID)
    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()
    checkout = parallel_checkout(context, stock, repository, workers)

    order_id = checkout.place_order("C-1234", "SKU-KB", 2, "4242424242424242")

    assert order_id == "ORD-C-1234-SKU-KB-2"
    assert stock.available_units("SKU-KB") == 3
    assert len(repository.saved()) == 1
    assert_the_children_came_home(context)
    write_structural_trace(context)


def assert_the_children_came_home(context: ContextVarNarrativeContext) -> None:
    """The merged children are under the span that launched them, in the caller's own trace."""
    root = context.capture_trace().roots[0]
    assert names(root.children) == [
        "InventoryService.reserve",
        "FraudCheckService.approve",
        "PaymentService.charge",
        "OrderRepository.save",
    ]
    reserve = root.children[0]
    assert reserve.span_context is not None
    assert root.span_context is not None
    assert reserve.span_context.trace_id == root.span_context.trace_id
    assert reserve.span_context.parent_span_id == root.span_context.span_id
    assert reserve.concurrency is not None
    assert reserve.concurrency.thread_name == "checkout-worker_0"


def test_a_task_submitted_without_the_handover_starts_a_new_trace(
    context: ContextVarNarrativeContext, workers: ThreadPoolExecutor
) -> None:
    context.adopt_trace_id(DEMO_TRACE_ID)
    stock = InventoryService("SKU-KB", 5)
    inventory = trace_object(stock, context)

    def reserve_and_report_the_trace() -> TraceId:
        inventory.reserve("SKU-KB", 2)
        return context.trace_id()

    # No ForkJoinGroup, no snapshot: the task is handed over, the trace is not.
    on_the_worker = workers.submit(reserve_and_report_the_trace).result()

    assert stock.available_units("SKU-KB") == 3
    assert on_the_worker != context.trace_id()
    assert "InventoryService.reserve" not in names(context.capture_trace().roots)


def parallel_checkout(
    context: ContextVarNarrativeContext,
    stock: InventoryService,
    repository: OrderRepository,
    workers: ThreadPoolExecutor,
) -> ParallelCheckout:
    inventory = trace_object(stock, context)
    fraud = trace_object(RuleBasedFraudCheck(), context, class_name="FraudCheckService")
    payments = trace_object(PaymentService(), context)
    orders = trace_object(repository, context)
    checkout = ParallelCheckout(context, inventory, fraud, payments, orders, workers)
    return trace_object(checkout, context, class_name="OrderService")


def names(nodes: list[TraceNode]) -> list[str]:
    return [f"{node.signature.class_name}.{node.signature.method_name}" for node in nodes]


def write_structural_trace(context: ContextVarNarrativeContext) -> None:
    """The caller's value-free structure, into the directory the page embeds from."""
    target = Path(os.environ[ARTIFACTS_ENV])
    target.mkdir(parents=True, exist_ok=True)
    document = StructuralTraceRenderer().render_document(
        context.capture_trace(), "The background tasks stay in the customers trace"
    )
    (target / "checkout.nt").write_text(document, encoding="utf-8")
```

## La salida real

**El log de la ejecución que conserva la traza:**

```text
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → OrderService.place_order(customer_id: "C-1234", sku: "SKU-KB", quantity: 2, card_number: [REDACTED])
DEBUG [MainThread] [narrativetrace] [] - ⑂ fork group created [groupId: fork-1]
DEBUG [checkout-worker_0] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → InventoryService.reserve(sku: "SKU-KB", quantity: 2)
DEBUG [checkout-worker_0] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: null
DEBUG [checkout-worker_0] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → FraudCheckService.approve(customer_id: "C-1234", amount_cents: 7998)
DEBUG [checkout-worker_0] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: True
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → InventoryService.reserve(sku: "SKU-KB", quantity: 2)
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: null
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → FraudCheckService.approve(customer_id: "C-1234", amount_cents: 7998)
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: True
DEBUG [MainThread] [narrativetrace] [] - ⑃ fork joined [groupId: fork-1, members: 2]
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → PaymentService.charge(customer_id: "C-1234", amount_cents: 7998, card: [REDACTED])
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: "PAY-C-1234-7998"
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - → OrderRepository.save(order: Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998))
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: null
DEBUG [MainThread] [narrativetrace] [c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7] - ← returned: "ORD-C-1234-SKU-KB-2"
```

**La traza estructural de esa ejecución:**

```text
scenario: The background tasks stay in the customers trace

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) → value
  ~ fork [2]
    #1.1 - FraudCheckService.approve(customer_id, amount_cents) → value
    #1.2 - InventoryService.reserve(sku, quantity) → value
  #1.3 - PaymentService.charge(customer_id, amount_cents, card) → value
  #1.4 - OrderRepository.save(order) → value
```

La misma traza renderizada como Markdown (lo que escribe el plugin de pytest
para una prueba que usa su fixture `narrative_trace`) lleva tres cosas más — el
nombre del hilo worker junto a cada hijo, el tiempo de reloj del join, y una
pista de "async secuencial" cuando las tareas no se solaparon — y no se incrusta
aquí porque los números que contiene cambian en cada ejecución.

## Cómo leerlo

- **La entrega es visible, dos veces.**
  `⑂ fork group created [groupId: fork-1]` es el grupo creándose, antes de que
  se envíe ninguna de las tareas; `⑃ fork joined [groupId: fork-1, members: 2]`
  es `merge()` informando de lo que volvió. Entre ambas hay trabajo en segundo
  plano que pertenece a este checkout. Esas dos líneas llevan un id de traza
  vacío — el último corchete es `[]` — porque no son eventos de span: son el
  ciclo de vida propio del grupo, publicado por el contexto y no por una
  llamada trazada.
- **Las líneas de los hijos llevan el id de traza del cliente, en el hilo del
  worker.** `InventoryService.reserve` y `FraudCheckService.approve` se
  escriben desde `[checkout-worker_0]` con
  `[c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7]` — el mismo id que cada línea
  `[MainThread]` por encima y por debajo de ellas. Esa es la instantánea que
  `group.wrap` tomó en el momento del envío, activada en el worker.
- **Cada hijo aparece dos veces en el log, y una vez en la traza.** El primer
  par es el trabajo ocurriendo, en `checkout-worker_0`. El segundo par — las
  mismas dos llamadas, los mismos valores, en `MainThread`, justo antes de la
  línea del join — es `merge()` republicándolas bajo el span que las lanzó, que
  es lo que las pone en el árbol de quien llama. Lee el log como un log: dos
  escrituras, un evento cada una. Lee el `.nt` como el registro: `#1.1` y
  `#1.2` bajo `#1`, dentro de `~ fork [2]`, exactamente una vez.
- **El id del span padre de cada hijo es el span que lanzó.** `#1.1` y `#1.2`
  nombran a `#1` como su padre — no porque se ejecutaran bajo él en el mismo
  hilo (no lo hicieron) sino porque el grupo los injertó ahí. Una línea de log
  no puede mostrar esto como un valor estable (un span id se genera por span y
  cambiaría en cada ejecución), así que `assert_the_children_came_home` de
  arriba lo afirma: el `parent_span_id` de cada hijo es el `span_id` de la
  raíz, el `trace_id` de cada hijo es el de la raíz, y el hilo registrado es
  `checkout-worker_0`. Esa aserción es la prueba de esta página.
- **En qué se diferencia la segunda ejecución.** Envía la misma llamada
  trazada sin wrap y el hilo worker no tiene ninguna instantánea que activar,
  así que su primera llamada trazada hace lo que hace cualquier primera llamada
  trazada: empieza una traza. La segunda prueba afirma las dos consecuencias —
  el id de traza observado *en el worker* no es el de quien llama, y la traza
  capturada de quien llama no contiene ningún `InventoryService.reserve`. El
  trabajo sigue ocurriendo, el stock sigue reservándose, las líneas siguen
  registrándose. Simplemente son la historia de otro, bajo un id que nadie está
  buscando. El log de esa ejecución no se incrusta por la misma razón: el id de
  sus líneas es nuevo cada vez, y ese es el hallazgo.
- **Por qué "esperado secuencialmente" es el diagnóstico correcto aquí.** El
  pool de este escenario tiene un hilo, así que las dos tareas se ejecutan de
  verdad una tras otra y el renderizado Markdown lo dice. Eso es una propiedad
  de este escenario, elegida para que el log de una ejecución sea lo bastante
  estable byte a byte como para incrustarlo — no de la entrega, que es el mismo
  código para un pool de cualquier tamaño.

## Qué no se captura

- **El trabajo iniciado sin la entrega empieza una traza nueva.** Esa es toda
  la segunda mitad de esta página: sin wrap, sin instantánea, sin id de traza
  compartido. Nada te avisa, porque desde el punto de vista de la biblioteca un
  hilo nuevo con una llamada trazada encima es una traza nueva ordinaria.
- **Un framework que propaga el contexto por sí mismo está cubierto solo
  donde lo diga su integración.** El middleware ASGI enlaza el contexto de la
  petición para la propia tarea de la petición; el trabajo que empujas a un
  pool de hilos desde un handler sigue siendo tuyo para envolver. Fuera de lo
  que enumera la [Guía de funcionalidades](guia-de-funcionalidades.md), da por
  hecho que la entrega te toca escribirla a ti.
- **`capture_trace()` informa de la traza del contexto al que se le pregunta.**
  Una captura tomada desde la propia pila de un worker ve los spans de ese
  worker, no los de quien llama — por eso es el grupo, y no la consulta, lo que
  junta ambas cosas.
- **Un grupo sin `merge()` no recoge nada en la traza de quien llama.** Los
  hijos se registran, y luego nada los injerta: el log aún los muestra (con el
  id de traza correcto), el árbol de quien llama no.
- **El trabajo que sobrevive a la llamada es otro helper.** `FireAndForgetGroup`
  no tiene paso de merge por diseño — el método que lanzó ya ha retornado, así
  que no queda nadie con quien fusionar.
- **Entrelazado.** Con un pool real las líneas de los hijos llegan en el orden
  en que se planifiquen los hilos, por lo que un log se lee por id de traza y
  no por posición. Los artefactos de traza no se ven afectados: la filiación
  viene de la instantánea, no del orden en que se escribieron las líneas.

**La skill para esto:** `narrativetrace-verify` — "runs async" y "crosses
threads" son dos de los casos para los que existe, y lee la traza estructural
contra la intención antes de dar nada por terminado.
