# Review a refactoring: did behaviour change

## The problem

> I refactored the checkout. The tests are green. Did the behaviour change?

Green means no assertion noticed. A refactoring that drops a call nobody
asserts on is green and wrong, and this is the common shape of it: the
compensating call on an error path, which no happy-path test reaches.

## Minimal setup

Beyond the [install](../guides/installation.md), approval mode — one setting,
and a directory of committed approved traces:

```bash
NARRATIVETRACE_APPROVAL=true uv run pytest   # compare, don't just write; NARRATIVETRACE_APPROVED_DIR defaults to test-narratives
```

The first run of each test writes
`test-narratives/<module>/<test>.received.nt` and fails; you read it, run
`uv run poe approve` (the `narrativetrace-approve` console script) to promote
every reviewed received trace to an `.approved.nt`, and commit those. See
[Configuration Guide, structural artifact and approval mode](../guides/configuration.md#structural-artifact-and-approval-mode)
and [What to Commit](../what-to-commit.md#approval-mode-visually).

## The scenario

The test pins the error path a refactoring is most likely to break — a
declined card must save no order — and it passes against both versions of the
checkout, which is the whole problem:

<!-- snippet: examples/recipes/checkout/refactored_checkout_fixture.py -->
```python
"""The test documentation/recipes/review-a-refactoring-did-behaviour-change.md pins: a declined card
must save no order. It passes before and after the refactoring -- which is the whole point of the
page -- so only the approved structure can object.

A fixture because ``recipe_artifacts.py`` runs it twice under approval mode, once per version of the
checkout, and reads the verdicts. ``NARRATIVETRACE_RECIPE_REFACTORED`` picks the version: in your
project the refactoring is an edit to one file and this switch does not exist.
"""

import os

import pytest

from examples.recipes.checkout.domain import PaymentDeclinedError
from examples.recipes.checkout.env import REFACTORED_ENV
from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.order_service_without_release import OrderServiceWithoutRelease
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, trace_object

# A fixed trace id, so the page's embedded artifacts name the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")


def test_a_declined_card_saves_no_order(narrative_trace: ContextVarNarrativeContext) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()

    inventory = trace_object(stock, narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(repository, narrative_trace)
    service_class = OrderServiceWithoutRelease if os.environ.get(REFACTORED_ENV) else OrderService
    checkout = trace_object(
        service_class(inventory, payments, orders), narrative_trace, class_name="OrderService"
    )

    with pytest.raises(PaymentDeclinedError):
        checkout.place_order("C-1234", "SKU-KB", 2, PaymentService.DECLINING_CARD)

    assert repository.saved() == []
```
<!-- /snippet -->

## The actual output

The committed approved trace, at
`test-narratives/refactored_checkout_fixture/test_a_declined_card_saves_no_order.approved.nt`:

<!-- snippet: examples/recipes/checkout/test-narratives/refactored_checkout_fixture/test_a_declined_card_saves_no_order.approved.nt -->
```text
scenario: Test a declined card saves no order

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) !! PaymentDeclinedError
  #1.1 - InventoryService.reserve(sku, quantity) → value
  #1.2 - PaymentService.charge(customer_id, amount_cents, card) !! PaymentDeclinedError
  #1.3 - InventoryService.release(sku, quantity) → value
```
<!-- /snippet -->

The refactored run's verdict — the test's own assertions passed, the structure
did not, so pytest reports an error at the test's teardown:

<!-- snippet: examples/recipes/checkout/build/review-a-refactoring-did-behaviour-change/approval-rejection.txt -->
```text
Structure changed against the approved trace (-1 call InventoryService.release):
 scenario: Test a declined card saves no order
 
 #1 - OrderService.place_order(customer_id, sku, quantity, card_number) !! PaymentDeclinedError
   #1.1 - InventoryService.reserve(sku, quantity) → value
   #1.2 - PaymentService.charge(customer_id, amount_cents, card) !! PaymentDeclinedError
-  #1.3 - InventoryService.release(sku, quantity) → value
Received: examples/recipes/checkout/build/review-a-refactoring-did-behaviour-change/approved-after-the-refactoring/refactored_checkout_fixture/test_a_declined_card_saves_no_order.received.nt
If this change is intended, approve it (run `uv run poe approve` or `narrativetrace-approve`). → narrativetrace-doctor skill
```
<!-- /snippet -->

And the received trace it offers for review, which `uv run poe approve` would
promote:

<!-- snippet: examples/recipes/checkout/build/review-a-refactoring-did-behaviour-change/approved-after-the-refactoring/refactored_checkout_fixture/test_a_declined_card_saves_no_order.received.nt -->
```text
scenario: Test a declined card saves no order

#1 - OrderService.place_order(customer_id, sku, quantity, card_number) !! PaymentDeclinedError
  #1.1 - InventoryService.reserve(sku, quantity) → value
  #1.2 - PaymentService.charge(customer_id, amount_cents, card) !! PaymentDeclinedError
```
<!-- /snippet -->

(The path in `Received:` is this repository's own: the run that produces this
page points `NARRATIVETRACE_APPROVED_DIR` under `build/`, because the step that
writes a page may not write into the source tree. In your project it is
`test-narratives`, beside the approved trace.)

## How to read it

- **The first line names the change, not just the fact of it:**
  `-1 call InventoryService.release`. One call fewer, and which one.
- **The diff body is the pinned shape with the dropped line marked.** `#1`,
  `#1.1` and `#1.2` are unchanged and unmarked; `-  #1.3 - InventoryService.release(sku, quantity) → value`
  is the behaviour that left. A reviewer who has never seen this code can tell
  what the refactoring did from a few lines.
- **The test's own assertions passed.** The failure is the approval's, which is
  the point: the suite asserts that no order is saved, and the refactoring did
  not break that. Nothing in the test ever looked at the release, and nothing
  had to.
- **Now decide.** If dropping the release is intended — the caller took it
  over, say — run `uv run poe approve`, review the diff in the promoted file,
  and commit it: the new shape becomes the pinned one. If it is not intended,
  you have just caught the bug that
  [Help me debug and fix this bug](help-me-debug-and-fix-this-bug.md) fixed,
  on its way back in. Either way the decision is recorded in the repository,
  by a human, in a file a reviewer can read.
- **The approved trace is value-free**, so approving it leaks nothing and a
  change in test data never makes it fail: `(customer_id, sku, quantity,
  card_number)` are names, `!! PaymentDeclinedError` is an outcome.

This is the approval-testing idea, applied to traces: the committed
artifact is the shape of the behaviour, not a snapshot of its values.

## What is not captured

- **This is a structural comparison: the same calls, in the same order, with
  the same outcomes.** It is not a proof that every value is equal. A
  refactoring that charges 7998 where it charged 3999, with every call in
  place, passes this gate — that is what your assertions are for, and the
  `DETAIL` artifact is where you would see it.
- **Only the calls the integration intercepts.** A dropped private call, or
  one between two unwrapped objects, is invisible to the approved trace
  exactly as it is to the trace.
- **A test that does not run is not compared.** Approval protects the
  scenarios you pinned; a flow with no test has no approved trace, and deleting
  a test deletes its gate (the `.approved.nt` is then an orphan, which
  `narrativetrace-doctor` reports).
- **Timings are never part of it.** The approved trace carries no durations,
  so it cannot catch a change that only made the flow slower.

**The skill for this:** `narrativetrace-verify` — it reads the structural
trace against the intent of the change and pins the flow as an approved trace
behind your yes.
