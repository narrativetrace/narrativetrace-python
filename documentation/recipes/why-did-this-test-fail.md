# Why did this test fail

## The problem

> Why did this test fail?

One checkout test is red. The assertion says what did not match; it does not
say what the code did on the way there, which is the part you need in order
to know whether the code or the expectation is wrong.

## Minimal setup

Nothing beyond the [install](../guides/installation.md). The `narrative_trace`
fixture of [`narrativetrace-pytest`](../guides/pytest.md) writes one narrative
per test with no configuration — for a failing test too, which is the case this
page is about. The files land in `narrative-traces/traces/<module>/<test>.md`,
and `narrative-traces/manifest.json` lists every artifact of every scenario
when you know the test's name but not its file's.

## The scenario

The failing test:

<!-- snippet: examples/recipes/checkout/stale_expectation_fixture.py -->
```python
"""The failing checkout test documentation/recipes/why-did-this-test-fail.md is read through. It
fails on an assertion, by design, which is why it is a fixture (not collected as a ``test_*``
module): ``recipe_artifacts.py`` runs it in its own pytest process and records what the run
reported.

Nothing here says which side is wrong -- that is the reader's exercise, and the narrative the run
writes is what settles it. Do not add a comment that gives it away.
"""

from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, trace_object

# A fixed trace id, so the page's embedded artifact names the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")


def test_the_customer_gets_an_order_id_for_their_keyboards(
    narrative_trace: ContextVarNarrativeContext,
) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    inventory = trace_object(InventoryService("SKU-KB", 5), narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(OrderRepository(), narrative_trace)
    checkout = trace_object(OrderService(inventory, payments, orders), narrative_trace)

    order_id = checkout.place_order("C-1234", "SKU-KB", 2, "4242424242424242")

    assert order_id == "ORD-C-1234-SKU-KB-1"
```
<!-- /snippet -->

## The actual output

What the runner reported:

<!-- snippet: examples/recipes/checkout/build/why-did-this-test-fail/assertion-failure.txt -->
```text
assert 'ORD-C-1234-SKU-KB-2' == 'ORD-C-1234-SKU-KB-1'
  
  - ORD-C-1234-SKU-KB-1
  ?                   ^
  + ORD-C-1234-SKU-KB-2
  ?                   ^
```
<!-- /snippet -->

And what the same run wrote beside it, at
`narrative-traces/traces/stale_expectation_fixture/test_the_customer_gets_an_order_id_for_their_keyboards.md`:

<!-- snippet: examples/recipes/checkout/build/why-did-this-test-fail/traces/stale_expectation_fixture/test_the_customer_gets_an_order_id_for_their_keyboards.md mask=duration,traceName -->
```text
---
type: trace
run: neat wheel lands
scenario: Test the customer gets an order id for their keyboards
entry_point: OrderService.place_order
duration_ms: 2
trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
trace_name: solid wand romps
method_count: 4
error_count: 0
---

## Trace: solid wand romps — OrderService.place_order

**Scenario:** Test the customer gets an order id for their keyboards
**Duration:** 2ms | **Result:** FAILED

### Call Flow

- **OrderService.place_order**(customer_id: `"C-1234"`, sku: `"SKU-KB"`, quantity: `2`, card_number: `[REDACTED]`) — 2ms #1
  - **InventoryService.reserve**(sku: `"SKU-KB"`, quantity: `2`) → `null` — 0ms #1.1
  - **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, card: `[REDACTED]`) → `"PAY-C-1234-7998"` — 0ms #1.2
  - **OrderRepository.save**(order: `Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998)`) → `null` — 0ms #1.3
  - → `"ORD-C-1234-SKU-KB-2"`
```
<!-- /snippet -->

## How to read it

Read the narrative top-down against the assertion, one span at a time:

- `#1 OrderService.place_order(... quantity: 2 ...) → "ORD-C-1234-SKU-KB-2"`.
  The value the assertion rejected is right there, and so is the input that
  produced it: the call asked for **two** keyboards.
- `#1.1 InventoryService.reserve(sku: "SKU-KB", quantity: 2)` — two units
  reserved, consistent with the call.
- `#1.2 PaymentService.charge(..., amount_cents: 7998, ...)` — 7998 is two
  units at 3999, so the price agrees with the quantity too.
- `#1.3 OrderRepository.save(order: Order(... quantity=2 ...))` — what was
  stored agrees with what was asked for.
- `**Result:** FAILED` in the header is the *test's* verdict, not the code's:
  `error_count: 0` and every span completed. Nothing raised.

Every span agrees with every other span and with the call that started them.
The expectation — `ORD-C-1234-SKU-KB-1` — is the only thing in the run that
says one keyboard, so it is the thing that is out of date; the fixture it was
written against has since changed to order two. The fix is in the test.

The opposite reading is the other recipe: when a span *disagrees* with the
intent — a quantity that changes between two calls, a call that should have
followed and did not — the code is wrong, and
[Help me debug and fix this bug](help-me-debug-and-fix-this-bug.md) is that
walk-through.

## What is not captured

- **Only that test's run.** The narrative is written per test, per run. A
  failure that happens once in twenty runs needs one of those runs to be the
  one that wrote the file; each run overwrites the previous run's file, and a
  failing run does not advance the value-free `.nt` baseline at all.
- **The assertion is not in the trace.** The two outputs above come from two
  places — the runner reported the mismatch, the plugin wrote the flow — and
  nothing correlates them automatically beyond the scenario name.
- **A value a test computed but never passed to a traced call is invisible.**
  The trace carries parameters and return values of wrapped calls, not local
  variables.
- **Timings in a failing run mean nothing.** The run stopped being
  representative the moment the assertion raised.

**The skill for this:** `narrativetrace-debug` — it starts from the symptom,
reads the first span where a value diverges, and names it by span id.
