# Help me debug and fix this bug

## The problem

> Help me debug and fix this bug: a customer's card was declined and the
> keyboard never came back into stock.

The error the team has is `PaymentDeclinedError: card declined by the issuer`,
which is not the bug. The bug is what the checkout did *after* it.

## Minimal setup

Nothing beyond the [install](../guides/installation.md): the `narrative_trace`
fixture of [`narrativetrace-pytest`](../guides/pytest.md) writes one trace per
test with no configuration. The last step on this page — pinning the fixed
flow — turns on approval mode, which is one setting:

```bash
NARRATIVETRACE_APPROVAL=true uv run pytest   # compare each passing test's structure with its committed approved trace
```

See [Configuration Guide, structural artifact and approval mode](../guides/configuration.md#structural-artifact-and-approval-mode)
and [What to Commit](../what-to-commit.md#approval-mode-visually).

## The scenario

Reproduce it in the smallest test that can fail for this reason — a declined
card must leave the stock as it found it:

<!-- snippet: examples/recipes/checkout/declined_payment_fixture.py -->
```python
"""The reproduction documentation/recipes/help-me-debug-and-fix-this-bug.md is written around: a
declined card must leave the stock as it found it.

The second test is the same reproduction against the checkout as it stood before the fix
(``OrderServiceWithoutRelease``), so the page's "before" trace comes from a real failing run rather
than from prose. It FAILS by design, which is why this module is a fixture (not collected as a
``test_*`` module): ``recipe_artifacts.py`` runs it in its own pytest process and records what the
run reported.

Both tests adopt the same fixed trace id, so the two artifacts a reader compares differ only where
the code differs.
"""

import pytest

from examples.recipes.checkout.domain import PaymentDeclinedError
from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.order_service_without_release import OrderServiceWithoutRelease
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, trace_object

# A fixed trace id, so the page's embedded artifacts name the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")


def test_the_stock_is_released_when_the_card_is_declined(
    narrative_trace: ContextVarNarrativeContext,
) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()

    inventory = trace_object(stock, narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(repository, narrative_trace)
    checkout = trace_object(OrderService(inventory, payments, orders), narrative_trace)

    with pytest.raises(PaymentDeclinedError):
        checkout.place_order("C-1234", "SKU-KB", 2, PaymentService.DECLINING_CARD)

    assert repository.saved() == []
    assert stock.available_units("SKU-KB") == 5


def test_the_stock_is_released_when_the_card_is_declined_before_the_fix(
    narrative_trace: ContextVarNarrativeContext,
) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()

    inventory = trace_object(stock, narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(repository, narrative_trace)
    checkout = trace_object(
        OrderServiceWithoutRelease(inventory, payments, orders),
        narrative_trace,
        class_name="OrderService",
    )

    with pytest.raises(PaymentDeclinedError):
        checkout.place_order("C-1234", "SKU-KB", 2, PaymentService.DECLINING_CARD)

    assert repository.saved() == []
    assert stock.available_units("SKU-KB") == 5
```
<!-- /snippet -->

The second test runs the same reproduction against the checkout as it stood
before the fix, which is the run the first trace below comes from. (This
repository keeps both in a fixture module that a pytest process of its own runs,
because the second test fails by design; in your project the failing test is
just your test.)

<!-- snippet: examples/recipes/checkout/order_service_without_release.py -->
```python
"""The same checkout with no release path: a declined charge leaves the reservation behind."""

from __future__ import annotations

from examples.recipes.checkout.domain import Order
from examples.recipes.checkout.order_service import UNIT_PRICE_CENTS
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService


class OrderServiceWithoutRelease:
    """Two recipe pages need this code to RUN, not to be described: ``help-me-debug-and-fix-this-
    bug`` (the bug, before its fix) and ``review-a-refactoring-did-behaviour-change`` (the
    refactoring that drops the release call while every test stays green). It is kept beside
    ``OrderService`` rather than reconstructed by a flag, so each page embeds real source and each
    run is a real run.

    Never the implementation to copy: ``OrderService`` is. A trace names the class it was told to
    name, and both are wrapped as ``OrderService``
    (``trace_object(..., class_name="OrderService")``) -- which is exactly what makes one approved
    trace comparable across the two.
    """

    def __init__(
        self, inventory: InventoryService, payments: PaymentService, orders: OrderRepository
    ) -> None:
        self._inventory = inventory
        self._payments = payments
        self._orders = orders

    def place_order(self, customer_id: str, sku: str, quantity: int, card_number: str) -> str:
        self._inventory.reserve(sku, quantity)
        amount_cents = UNIT_PRICE_CENTS * quantity
        self._payments.charge(customer_id, amount_cents, card_number)
        order_id = f"ORD-{customer_id}-{sku}-{quantity}"
        self._orders.save(Order(order_id, customer_id, sku, quantity, amount_cents))
        return order_id
```
<!-- /snippet -->

## The actual output

The failing run's own narrative, at
`narrative-traces/traces/declined_payment_fixture/test_the_stock_is_released_when_the_card_is_declined_before_the_fix.md`
(the first assertion that fails is `assert 3 == 5` — three units left of five
— and the narrative explains why):

<!-- snippet: examples/recipes/checkout/build/help-me-debug-and-fix-this-bug/traces/declined_payment_fixture/test_the_stock_is_released_when_the_card_is_declined_before_the_fix.md mask=duration,traceName -->
```text
---
type: trace
run: neat ram melts
scenario: Test the stock is released when the card is declined before the fix
entry_point: OrderService.place_order
duration_ms: 0
trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
trace_name: solid wand romps
method_count: 3
error_count: 2
---

## Trace: solid wand romps — OrderService.place_order

**Scenario:** Test the stock is released when the card is declined before the fix
**Duration:** 0ms | **Result:** FAILED

### Call Flow

- **OrderService.place_order**(customer_id: `"C-1234"`, sku: `"SKU-KB"`, quantity: `2`, card_number: `[REDACTED]`) — 0ms #1
  - **InventoryService.reserve**(sku: `"SKU-KB"`, quantity: `2`) → `null` — 0ms #1.1
  - **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, card: `[REDACTED]`) #1.2

    > ❌ `PaymentDeclinedError`: card declined by the issuer — 0ms
  - ❌ `PaymentDeclinedError`: card declined by the issuer
```
<!-- /snippet -->

The fix is one `except`: release what was reserved, then let the decline
propagate as before.

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

The same reproduction, now passing, against the fixed checkout:

<!-- snippet: examples/recipes/checkout/build/help-me-debug-and-fix-this-bug/traces/declined_payment_fixture/test_the_stock_is_released_when_the_card_is_declined.md mask=duration,traceName -->
```text
---
type: trace
run: neat ram melts
scenario: Test the stock is released when the card is declined
entry_point: OrderService.place_order
duration_ms: 0
trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
trace_name: solid wand romps
method_count: 4
error_count: 2
---

## Trace: solid wand romps — OrderService.place_order

**Scenario:** Test the stock is released when the card is declined
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **OrderService.place_order**(customer_id: `"C-1234"`, sku: `"SKU-KB"`, quantity: `2`, card_number: `[REDACTED]`) — 0ms #1
  - **InventoryService.reserve**(sku: `"SKU-KB"`, quantity: `2`) → `null` — 0ms #1.1
  - **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, card: `[REDACTED]`) #1.2

    > ❌ `PaymentDeclinedError`: card declined by the issuer — 0ms
  - **InventoryService.release**(sku: `"SKU-KB"`, quantity: `2`) → `null` — 0ms #1.3
  - ❌ `PaymentDeclinedError`: card declined by the issuer
```
<!-- /snippet -->

With approval mode on, the first run of the fixed test writes its value-free
structure beside the approved traces as a `.received.nt` and fails;
`uv run poe approve` (the `narrativetrace-approve` console script) promotes it to
the committed approved trace, which is now the shape of this flow:

<!-- snippet: examples/recipes/checkout/test-narratives/declined_payment_fixture/test_the_stock_is_released_when_the_card_is_declined.approved.nt -->
```text
scenario: Test the stock is released when the card is declined

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) !! PaymentDeclinedError
  #1.1 - InventoryService.reserve(sku, quantity) → value
  #1.2 - PaymentService.charge(customer_id, amount_cents, card) !! PaymentDeclinedError
  #1.3 - InventoryService.release(sku, quantity) → value
```
<!-- /snippet -->

## How to read it

In the failing trace:

- `#1 OrderService.place_order` ends with `❌ PaymentDeclinedError` and no
  return value: the call the customer made did not complete.
- `#1.1 InventoryService.reserve(sku: "SKU-KB", quantity: 2)` has no `❌` — it
  completed, and `→ null` is only Python saying it returned `None`. Two units
  are now held.
- `#1.2 PaymentService.charge` threw. Its parameters say what was attempted:
  `amount_cents: 7998` for the two units, `card: [REDACTED]`.
- **Nothing follows `#1.2`.** `#1` goes straight from the charge to its own
  failure, so the two units `#1.1` reserved are still held. That absence is
  the bug, and the exception message never mentions it — the trace is what
  makes an omission visible, because it shows the whole flow and not only the
  line that raised.

In the passing trace: `#1.3 InventoryService.release(sku: "SKU-KB", quantity: 2)`
now sits between the charge and the failure. `#1` still ends in the decline —
that is correct, the customer's card really was declined — and the stock is
back.

In the approved trace: the same four calls with their parameter *names* and no
values at all, which is why it can be committed and read in a review.
`→ value` on `reserve` and `release` says they returned something — Python's
`None` counts, there being no `void` — without saying what. `#1.3` is now part
of the pinned shape: a later change that drops the release makes a passing test
fail with a diff naming `InventoryService.release`, so this bug cannot silently
return. That is
[Review a refactoring: did behaviour change](review-a-refactoring-did-behaviour-change.md).

## What is not captured

- **The trace shows calls that happened, not calls that should have.** The
  missing `release` is an absence a reader infers from the flow; nothing in
  the artifact says "a call is missing". What the approved trace adds is the
  comparison that turns an absence into a build failure — once.
- **An exception swallowed inside unwrapped code is invisible.** Only the
  wrapped objects appear. A `try`/`except` inside `OrderService` that ate the
  decline and returned normally would show as a completed call.
- **The card number cannot be recovered** from the trace or the log. It is
  redacted at capture, by value here — the parameter is named `card`, so the
  name deny-list never saw it, and the number is Luhn-valid.
- **Timings are not evidence of a performance problem** in a test this small:
  they are whole milliseconds, and most of these calls round to `0`.

**The skill for this:** `narrativetrace-debug` — it reproduces the symptom
with the smallest input, names the span where the value or the call diverges,
fixes it there, and pins the flow as a regression test behind your approval.
