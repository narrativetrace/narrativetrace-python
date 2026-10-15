<!-- source: documentation/recipes/add-logging-to-this-service.md blob 31919267f2b6 | translated: 2026-10-11 | reviewed: - -->

# Añade logging a este servicio

## El problema

> Añade logging a este servicio.

El servicio es un checkout. Reserva stock, cobra una tarjeta y guarda un
pedido, y no contiene ni una sola sentencia de log:

```python
"""The checkout: reserve the stock, charge the card, save the order -- and release on a decline."""

from __future__ import annotations

from examples.recipes.checkout.domain import Order, PaymentDeclinedError
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService

UNIT_PRICE_CENTS = 3999


class OrderService:
    def __init__(
        self, inventory: InventoryService, payments: PaymentService, orders: OrderRepository
    ) -> None:
        self._inventory = inventory
        self._payments = payments
        self._orders = orders

    def place_order(self, customer_id: str, sku: str, quantity: int, card_number: str) -> str:
        self._inventory.reserve(sku, quantity)
        amount_cents = UNIT_PRICE_CENTS * quantity
        try:
            self._payments.charge(customer_id, amount_cents, card_number)
        except PaymentDeclinedError:
            self._inventory.release(sku, quantity)
            raise
        order_id = f"ORD-{customer_id}-{sku}-{quantity}"
        self._orders.save(Order(order_id, customer_id, sku, quantity, amount_cents))
        return order_id
```

Lo que de verdad quieres es aquello para lo que el logging es un medio: qué
hizo esta llamada, con qué valores lo hizo, en el log que tu equipo ya lee.
Así que la respuesta de abajo tampoco escribe ninguna sentencia de log.

## Configuración mínima

Además de la [instalación](guia-de-instalacion.md) — `narrativetrace` para el
wrapper y el puente de `logging`, `narrativetrace-pytest` para la prueba en la
que se ejecuta esta página — esta página necesita una pieza de configuración
ordinaria de `logging`, de la que ya tiene una app real (`handler` abajo es el
handler que ya configure). La única línea de NarrativeTrace es el filtro que
deja `traceName` disponible para el formato:

```python
handler.addFilter(NarrativeContextFilter())  # makes traceName available to the format below
logging.basicConfig(
    level=logging.DEBUG,  # the bridge logs every call at DEBUG; INFO would hide all of it
    format="%(levelname)-5s [%(traceName)s] [%(name)s] - %(message)s",
    handlers=[handler],
)
```

`NarrativeContextFilter` estampa el propio nombre de la traza en cada registro,
y el formato lo lee. El nivel es `DEBUG` porque el puente registra cada llamada
en `DEBUG` — el `logging` de Python no tiene `TRACE`. A dónde van los
registros lo decide el handler, no NarrativeTrace.

## El escenario

Cada colaborador se envuelve una sola vez, donde se construye — el checkout
mismo el último, de modo que las llamadas a través de él se capturan antes de
llegar a la implementación real. Tras la llamada, `export_to_logger` reproduce
la traza capturada a través del logger configurado arriba. Nada más cambia:

```python
"""documentation/recipes/add-logging-to-this-service.md's scenario: the checkout, with no log
statement anywhere in it, logs every call through the project's own ``logging`` setup once its
collaborators are wrapped.

A fixture, not a ``test_*`` module: ``recipe_artifacts.py`` runs it in its own pytest process so the
log file the page embeds holds this scenario alone.
"""

from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, export_to_logger, trace_object

# A fixed trace id, adopted so this page's embedded output names the same trace every run -- the
# mechanism a boundary uses for an inbound trace header. A real run generates a random id.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")


def test_a_customer_checks_out(narrative_trace: ContextVarNarrativeContext) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()

    inventory = trace_object(stock, narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(repository, narrative_trace)
    checkout = trace_object(OrderService(inventory, payments, orders), narrative_trace)

    order_id = checkout.place_order("C-1234", "SKU-KB", 2, "4242424242424242")

    export_to_logger(narrative_trace.capture_trace())

    assert order_id == "ORD-C-1234-SKU-KB-2"
    assert stock.available_units("SKU-KB") == 3
    assert len(repository.saved()) == 1
```

El escenario es una prueba de pytest porque ahí es donde ya se ejercita un
flujo como este (este repositorio lo ejecuta como un módulo fixture en su
propio proceso de pytest, de modo que el log de abajo contiene este escenario
y nada más — de ahí los imports `examples.…` y el nombre del módulo); el mismo
cableado funciona en un script, un handler de `FastAPI` o un worker. El
fixture `narrative_trace` es el que escribe los artefactos de traza por prueba
que leen las demás recetas.

## La salida real

El log que escribió la ejecución anterior, a través del logger propio del
proyecto:

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

## Cómo leerlo

- `→` abre una llamada, `←` cierra la abierta más recientemente, así que la
  indentación es innecesaria: el primer `→ OrderService.place_order` y el
  último `← returned: "ORD-C-1234-SKU-KB-2"` son la misma llamada, y todo lo
  que hay entre ellos ocurrió dentro de ella. En los artefactos de traza las
  mismas cuatro llamadas llevan los span ids `#1`, `#1.1`, `#1.2` y `#1.3` —
  [Revisa un flujo complejo antes de cambiarlo](revisa-un-flujo-complejo-antes-de-cambiarlo.md)
  las lee así.
- Cada línea lleva los *nombres* de parámetro que declara el método, que es lo
  que la convierte en una frase y no en una tupla: `reserve(sku: "SKU-KB", quantity: 2)`
  no necesita leyenda. Un argumento dataclass se renderiza campo por campo —
  `Order(order_id="ORD-C-1234-SKU-KB-2", …)`.
- `← returned: null` es un método que devolvió `None` — Python no tiene
  `void`, así que un método que no devuelve nada igualmente devuelve algo, y
  el log lo dice. `← returned: "PAY-C-1234-7998"` lleva el valor: `charge`
  devuelve el propio id de la pasarela, y `amount_cents: 7998` es de donde
  sale el precio de dos teclados.
- Faltan dos valores. `card_number: [REDACTED]` se ocultó por su *nombre* — la
  lista de denegación siempre activa, sin decorador, sin configuración.
  `card: [REDACTED]`, una línea más abajo, se ocultó por su *valor*: el
  parámetro se llama `card`, que la lista de denegación no conoce, y el número
  que contenía es válido según Luhn, así que la regla de forma del valor lo
  atrapó igualmente. Consulta
  [Privacidad y ocultación](privacidad-y-ocultacion.md).
- `[solid wand romps]` es el propio nombre de la traza, de modo que cada línea
  de un checkout se puede extraer con grep de un log muy cargado.

La conclusión que esto respalda: la narrativa salió de los nombres de método,
los nombres de parámetro y los valores, y no se escribió ni una sola sentencia
de log para obtenerla.

## Qué no se captura

- **Solo se registra el código envuelto.** Arriba se envolvieron cuatro
  objetos, así que aparecen cuatro llamadas. Una llamada entre dos objetos sin
  envolver — o un método privado dentro de `OrderService` — es invisible aquí.
  Si envolver a mano cada colaborador no es lo que quieres, los decoradores y
  el middleware ASGI se acoplan sin tocar el código de construcción:
  [Eligiendo una integración](eligiendo-una-integracion.md).
- **Un valor que coincide con las reglas de ocultación se reemplaza antes de
  escribirse,** también en esta línea de log. Eso no se puede configurar a la
  baja, y significa que un parámetro oculto no se puede recuperar del log.
- **El nivel propio del logger sigue aplicándose.** Estos registros son
  `DEBUG`; con el handler en `INFO` el log queda vacío y nada te avisa.
- **Las líneas se escriben cuando se ejecuta `export_to_logger`,** después de
  que la llamada haya devuelto o lanzado, así que un proceso que muere a mitad
  de una llamada no registra nada de ella. Para obtener las líneas a medida que
  ocurren las llamadas, acopla en su lugar el consumidor en vivo:
  [Guía de logging](guia-de-logging.md).
- **Los tiempos no están en las líneas de log.** La duración de cada llamada
  está en los artefactos de traza, no aquí.

**La skill para esto:** `add-narrative-tracing` — instala los paquetes, envuelve
la primera clase y comprueba el cableado con `narrativetrace-doctor`.
