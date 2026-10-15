# Add logging to this service

## The problem

> Add logging to this service.

The service is a checkout. It reserves stock, charges a card and saves an
order, and it contains no log statement at all:

<!-- snippet: examples/recipes/checkout/order_service.py -->
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
<!-- /snippet -->

What you actually want is the thing logging is a means to: what this call
did, with the values it did it with, in the log your team already reads. So
the answer below writes no log statement either.

## Minimal setup

Beyond the [install](../guides/installation.md) — `narrativetrace` for the
wrapper and the `logging` bridge, `narrativetrace-pytest` for the test this
page runs in — this page needs one piece of ordinary `logging` configuration,
the kind a real app already has (`handler` below is whichever handler it
already configures). The only NarrativeTrace line in it is the filter that
makes `traceName` available to the format:

<!-- snippet: examples/recipes/checkout/conftest.py region=logging -->
```python
handler.addFilter(NarrativeContextFilter())  # makes traceName available to the format below
logging.basicConfig(
    level=logging.DEBUG,  # the bridge logs every call at DEBUG; INFO would hide all of it
    format="%(levelname)-5s [%(traceName)s] [%(name)s] - %(message)s",
    handlers=[handler],
)
```
<!-- /snippet -->

`NarrativeContextFilter` stamps the trace's own name onto every record, and the
format reads it. The level is `DEBUG` because the bridge logs every call at
`DEBUG` — Python's `logging` has no `TRACE`. Where the records go is the
handler's decision, not NarrativeTrace's.

## The scenario

Each collaborator is wrapped once, where it is constructed — the checkout
itself last, so calls through it are captured before they reach the real
implementation. After the call, `export_to_logger` replays the captured trace
through the logger configured above. Nothing else changes:

<!-- snippet: examples/recipes/checkout/add_logging_fixture.py -->
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
<!-- /snippet -->

The scenario is a pytest test because that is where a flow like this is already
exercised (this repository runs it as a fixture module in its own pytest
process, so the log below holds this scenario alone — hence the `examples.…`
imports and the module's name); the same wiring works in a script, a
`FastAPI` handler or a worker. The `narrative_trace` fixture is what writes the
per-test trace artifacts the other recipes read.

## The actual output

The log the run above wrote, through the project's own logger:

<!-- snippet: examples/recipes/checkout/build/add-logging-to-this-service/checkout.log -->
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
<!-- /snippet -->

## How to read it

- `→` opens a call, `←` closes the one most recently opened, so indentation
  is unnecessary: the first `→ OrderService.place_order` and the last
  `← returned: "ORD-C-1234-SKU-KB-2"` are the same call, and everything
  between them happened inside it. In the trace artifacts the same four calls
  carry the span ids `#1`, `#1.1`, `#1.2` and `#1.3` —
  [Review a complex flow before changing it](review-a-complex-flow-before-changing-it.md)
  reads them that way.
- Every line carries the parameter *names* the method declares, which is what
  makes it a sentence rather than a tuple: `reserve(sku: "SKU-KB", quantity: 2)`
  needs no legend. A dataclass argument renders field by field —
  `Order(order_id="ORD-C-1234-SKU-KB-2", …)`.
- `← returned: null` is a method that returned `None` — Python has no `void`,
  so a method that returns nothing still returns something, and the log says
  so. `← returned: "PAY-C-1234-7998"` carries the value: `charge` returning the
  gateway's own id, and `amount_cents: 7998` is where the price of two
  keyboards comes from.
- Two values are gone. `card_number: [REDACTED]` was hidden by its *name* —
  the always-on deny-list, no decorator, no configuration. `card: [REDACTED]`
  one line down was hidden by its *value*: the parameter is named `card`,
  which the deny-list does not know, and the number it held is Luhn-valid, so
  the value-shape rule caught it anyway. See
  [Privacy and Redaction](../privacy-and-redaction.md).
- `[solid wand romps]` is the trace's own name, so every line of one checkout
  can be grepped out of a busy log.

The conclusion this supports: the narrative came from the method names, the
parameter names and the values, and not one log statement was written to get
it.

## What is not captured

- **Only wrapped code is logged.** Four objects were wrapped above, so four
  calls appear. A call between two unwrapped objects — or a private method
  inside `OrderService` — is invisible here. If wrapping every collaborator by
  hand is not what you want, the decorators and the ASGI middleware attach
  without touching construction code: [Choosing an Integration](../choosing-an-integration.md).
- **A value matching the redaction rules is replaced before it is written,**
  including in this log line. That is not configurable downward, and it means
  a redacted parameter cannot be recovered from the log.
- **The logger's own level still applies.** These records are `DEBUG`; with the
  handler at `INFO` the log is empty and nothing warns you.
- **The lines are written when `export_to_logger` runs,** after the call has
  returned or raised, so a process that dies in the middle of a call logs
  nothing for it. For lines as the calls happen, attach the live consumer
  instead: [Logging Guide](../guides/logging.md).
- **Timings are not in the log lines.** Each call's duration is in the trace
  artifacts, not here.

**The skill for this:** `add-narrative-tracing` — it installs the packages,
wraps the first class, and checks the wiring with `narrativetrace-doctor`.
