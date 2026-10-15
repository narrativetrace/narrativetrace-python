# Review a complex flow before changing it

## The problem

> Before you change the checkout, tell me what it actually does.

Reading the source answers what it *can* do. One run answers what it *does*
with these inputs — in what order, with which values, and where the flow
leaves the code you are about to edit. This page deliberately never shows the
implementation: that is the point of reading a run instead.

## Minimal setup

Nothing beyond the [install](../guides/installation.md) for the two trace
artifacts. The log lines need one piece of ordinary `logging` configuration,
exactly as in [Add logging to this service](add-logging-to-this-service.md).
The capture level is one setting, and `SUMMARY` is the one this page uses
beside the default `DETAIL`:

```bash
NARRATIVETRACE_LEVEL=SUMMARY uv run pytest   # OFF | ERRORS | SUMMARY | NARRATIVE | DETAIL
```

See [Configuration Guide, tracing level](../guides/configuration.md#tracing-level).

## The scenario

One representative run of the flow — an existing test is the cheapest one to
borrow, and this is that test:

<!-- snippet: examples/recipes/checkout/checkout_review_fixture.py -->
```python
"""One successful checkout, the flow
documentation/recipes/review-a-complex-flow-before-changing-it.md is read before changing anything.

A fixture because two readers need the same run under different settings: ``recipe_artifacts.py``
runs it in its own pytest process once at DETAIL and once at SUMMARY. It passes either way --
nothing here fails by design. The log lines are the same flow through the project's own ``logging``
setup (``conftest.py``).
"""

from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, export_to_logger, trace_object

# A fixed trace id, so the page's embedded artifacts name the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")


def test_a_customer_buys_two_keyboards(narrative_trace: ContextVarNarrativeContext) -> None:
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

## The actual output

**At `DETAIL`** (the default), `narrative-traces/traces/checkout_review_fixture/test_a_customer_buys_two_keyboards.md`:

<!-- snippet: examples/recipes/checkout/build/review-a-complex-flow-before-changing-it/detail/traces/checkout_review_fixture/test_a_customer_buys_two_keyboards.md mask=duration,traceName -->
```text
---
type: trace
run: meaty pier walks
scenario: Test a customer buys two keyboards
entry_point: OrderService.place_order
duration_ms: 0
trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
trace_name: solid wand romps
method_count: 4
error_count: 0
---

## Trace: solid wand romps — OrderService.place_order

**Scenario:** Test a customer buys two keyboards
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **OrderService.place_order**(customer_id: `"C-1234"`, sku: `"SKU-KB"`, quantity: `2`, card_number: `[REDACTED]`) — 0ms #1
  - **InventoryService.reserve**(sku: `"SKU-KB"`, quantity: `2`) → `null` — 0ms #1.1
  - **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, card: `[REDACTED]`) → `"PAY-C-1234-7998"` — 0ms #1.2
  - **OrderRepository.save**(order: `Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998)`) → `null` — 0ms #1.3
  - → `"ORD-C-1234-SKU-KB-2"`
```
<!-- /snippet -->

**At `SUMMARY`**, the same run of the same test:

<!-- snippet: examples/recipes/checkout/build/review-a-complex-flow-before-changing-it/summary/traces/checkout_review_fixture/test_a_customer_buys_two_keyboards.md mask=duration,traceName -->
```text
---
type: trace
run: quiet nib trims
scenario: Test a customer buys two keyboards
entry_point: OrderService.place_order
duration_ms: 0
trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
trace_name: solid wand romps
method_count: 4
error_count: 0
---

## Trace: solid wand romps — OrderService.place_order

**Scenario:** Test a customer buys two keyboards
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **OrderService.place_order**(customer_id: ``, sku: ``, quantity: ``, card_number: `[REDACTED]`) — 0ms #1
  - **InventoryService.reserve**(sku: ``, quantity: ``) → `null` — 0ms #1.1
  - **PaymentService.charge**(customer_id: ``, amount_cents: ``, card: ``) → `"PAY-C-1234-7998"` — 0ms #1.2
  - **OrderRepository.save**(order: ``) → `null` — 0ms #1.3
  - → `"ORD-C-1234-SKU-KB-2"`
```
<!-- /snippet -->

**The log the same flow wrote** through the project's own logger, values and
all:

<!-- snippet: examples/recipes/checkout/build/review-a-complex-flow-before-changing-it/detail/checkout.log -->
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

**The structural trace of that run**, `narrative-traces/structural/checkout_review_fixture/test_a_customer_buys_two_keyboards.nt`:

<!-- snippet: examples/recipes/checkout/build/review-a-complex-flow-before-changing-it/detail/structural/checkout_review_fixture/test_a_customer_buys_two_keyboards.nt -->
```text
scenario: Test a customer buys two keyboards

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) → value
  #1.1 - InventoryService.reserve(sku, quantity) → value
  #1.2 - PaymentService.charge(customer_id, amount_cents, card) → value
  #1.3 - OrderRepository.save(order) → value
```
<!-- /snippet -->

## How to read it

**The flow, from the `DETAIL` artifact.** `#1` is the call the test made and
the only root: everything indented under it happened inside it, in the order
printed. `#1.1` reserves two units before anything is charged; `#1.2` charges
7998 — two units at 3999, so the price is derived from the quantity and not
passed in; `#1.3` saves an order that already carries the id `#1` returns.
Read as a sentence: this checkout reserves first, charges second, saves third,
and the order id is minted before the save. A change that charges before it
reserves, or saves before it charges, is a change to *this*, and now you know
it without trusting a comment.

**What each level is for.** `DETAIL` carries the parameter values, and it is
what you read while working on the flow. At `SUMMARY` every parameter value
is empty — the backticks hold nothing — because it was suppressed at capture,
not hidden at render, and only roots and leaf calls are kept; this flow is two
levels deep, so no frame is intermediate and the same four calls appear. A
deeper flow loses its middle. Return values survive at every active level: the
return is the payload of a narrative. Use `SUMMARY` where the shape and the
outcomes are what you need and the values are cost — a CI run, a long soak —
and `OFF`/`ERRORS` in production until you need more.

**Which output a human reads, and which an agent reads.** The log lines are
for the human on call: they interleave with everything else the service logs,
carry the values, and are keyed by the trace's name — `[solid wand romps]` —
so one checkout can be grepped out of a busy file. The `.nt` is for the agent
and the reviewer: **value-free by construction** — compare it with the log
line above and the difference is not that the values were replaced but that
they were never written. `(customer_id, sku, quantity, card_number)` is the
parameter *names*; `→ value` says a value was returned without saying which
(on `reserve` and `save` it is Python's `None`, which still counts — there is
no `void`). That is what makes it safe to commit, to diff in a review, and to
hand to a model: it cannot leak a customer id, and it does not change when the
data changes — only when the *calls* change. Pinning it is
[Review a refactoring: did behaviour change](review-a-refactoring-did-behaviour-change.md).

## What is not captured

- **Calls inside unwrapped objects.** Four objects were wrapped; a call
  between two objects behind them, or a private method, never appears. A flow
  that looks shallow may be deep.
- **What the chosen integration does not intercept.** `trace_object` sees
  calls made *through* the wrapper only: an inner call that an object makes on
  itself (`self._helper()`) is invisible to it, where a decorator on that
  method would see it. [Choosing an Integration](../choosing-an-integration.md)
  is the trade-off per path, and this is the part of it that changes what you
  can read here.
- **Work that left the thread.** A call handed to an executor without the
  context travels no further; the trace ends where the thread ended.
- **Values the deny-list or the value-shape rule caught**, here `card_number`
  and `card`, are `[REDACTED]` in both the log and the `DETAIL` artifact, and
  absent by construction from the `.nt`.
- **One run, not the contract.** Another input takes another path — an
  out-of-stock sku never reaches `#1.2` at all.

**The skill for this:** `narrativetrace-verify` — it writes the intent down
first, runs the smallest real path, and reads the value-free trace against
that intent before anything is called done.
