# Trace in production without the cost

## The problem

> I want this in production for the requests that go wrong. I am not paying
> for a full trace of every request that goes right.

That is one setting — the tracing level — and this page is the same run seen
through it twice: the declined-payment checkout at `DETAIL`, where every value
is captured, and at `ERRORS`, where only runs that failed survive at all.

## Minimal setup

One level, set wherever your deployment is configured. Both of these say the
same thing:

```toml
# narrativetrace.toml (or [tool.narrativetrace] in pyproject.toml, never both)
level = "ERRORS"   # "OFF" | "ERRORS" | "SUMMARY" | "NARRATIVE" | "DETAIL"
```

```bash
# or in the environment, which wins over the file
NARRATIVETRACE_LEVEL=ERRORS uv run pytest
```

In code it is `ContextVarNarrativeContext(NarrativeTraceConfig(level=TracingLevel.ERRORS))`
([Configuration Guide, tracing level](../guides/configuration.md#tracing-level)).

The level is NarrativeTrace's own dial and it sits at the front: a call it
filters out never becomes an event, for any consumer. Your logger's level is a
second, independent dial that decides what is *printed* —
[FAQ, "Two dials, two paths"](../faq.md#two-dials-two-paths) is the long
version, and the distinction matters here because raising a logger level saves
you log volume while changing nothing about capture.

## The scenario

The run is the declined-payment reproduction from
[Help me debug and fix this bug](help-me-debug-and-fix-this-bug.md) —
`reserve`, then `charge` raising, then `release` — reused unchanged, because
the subject of this page is the dial and not another flow. The driver below
runs it at both levels, and runs a *successful* checkout at both as well:

<!-- snippet: examples/recipes/checkout/recipe_artifacts.py region=cost -->
```python
def _cost() -> dict[str, Run]:
    """The declined-payment reproduction at both levels, and a checkout that succeeds at both."""
    declined = "test_the_stock_is_released_when_the_card_is_declined"
    return {
        "cost_detail": _at_level("detail", "declined_payment", declined),
        "cost_errors": _at_level("errors", "declined_payment", declined, level="ERRORS"),
        "cost_detail_successful": _at_level("detail-successful", "checkout_review"),
        "cost_errors_successful": _at_level("errors-successful", "checkout_review", level="ERRORS"),
    }


def _at_level(directory: str, module: str, test: str | None = None, level: str = "DETAIL") -> Run:
    """One fixture run into its own directory, at ``level`` (the default level is DETAIL)."""
    return _run_fixture(module, _settings(COST, directory, NARRATIVETRACE_LEVEL=level), test)
```
<!-- /snippet -->

Each call is one real pytest process with `narrativetrace-pytest` loaded, in a
directory of its own, with `NARRATIVETRACE_LEVEL` set the way a deployment
would set it.

## The actual output

**At `DETAIL`**, the declined run, every value captured:

<!-- snippet: examples/recipes/checkout/build/trace-in-production-without-the-cost/detail/traces/declined_payment_fixture/test_the_stock_is_released_when_the_card_is_declined.md mask=duration,traceName -->
```text
---
type: trace
run: jumpy brick arcs
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

**At `ERRORS`**, the same run of the same code:

<!-- snippet: examples/recipes/checkout/build/trace-in-production-without-the-cost/errors/traces/declined_payment_fixture/test_the_stock_is_released_when_the_card_is_declined.md mask=duration,traceName -->
```text
---
type: trace
run: limp pond mixes
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

- **OrderService.place_order**(customer_id: ``, sku: ``, quantity: ``, card_number: `[REDACTED]`) — 0ms #1
  - **InventoryService.reserve**(sku: ``, quantity: ``) → `null` — 0ms #1.1
  - **PaymentService.charge**(customer_id: ``, amount_cents: ``, card: ``) #1.2

    > ❌ `PaymentDeclinedError`: card declined by the issuer — 0ms
  - **InventoryService.release**(sku: ``, quantity: ``) → `null` — 0ms #1.3
  - ❌ `PaymentDeclinedError`: card declined by the issuer
```
<!-- /snippet -->

**And at `ERRORS`, a checkout that succeeded**: no artifact at all. There is
nothing to embed, which is the whole point — this repository's recipe tests
assert both halves of that claim, the file's absence at `ERRORS` and its
presence at `DETAIL`, so the emptiness is the level's doing and not a path that
was never right.

## How to read it

- **What `ERRORS` keeps.** The failed run, whole. `#1` raised, and an error
  node's subtree is kept intact — so `reserve` (`#1.1`), `charge` (`#1.2`) and
  `release` (`#1.3`) are all still there, including the two calls that
  returned normally. That is deliberate: the calls around a failure are what
  you need to diagnose it, and dropping the successful sibling would leave you
  with an exception and no story. A call that returned *and* leads to no
  failure anywhere below it is dropped, and a root with no failure in its
  whole subtree is dropped entirely — which is why the successful checkout
  wrote nothing.
- **What `ERRORS` drops.** Every parameter value: where `DETAIL` printed
  `customer_id: "C-1234"` in a code span, `ERRORS` prints `customer_id:` and an
  empty code span. The value was never rendered, so it cannot be recovered from
  these events afterwards, at any later level. What survives is the shape, the
  outcomes (`reserve` and `release` still say `→ null`) and the exception, and
  `card_number` still reads `[REDACTED]` because redaction is a different
  decision from suppression.
- **The pruning happens after capture, not instead of it.** Every call was
  intercepted and every event was published; the tree is then built and what
  the level does not keep is removed. That is the honest shape of the cost:
  `ERRORS` is cheaper than `DETAIL` because values are not rendered — the
  expensive part — not because calls go unintercepted.
- **Only `OFF` skips interception.** At `OFF` the wrapper's check of
  `context.is_active()` returns before any capture, event or publish happens,
  and nothing downstream can bring the call back — a test in this repository
  asserts that a call at `OFF` leaves the captured trace empty. `ERRORS`,
  `SUMMARY` and `NARRATIVE` all still intercept every call. If the question is
  "what does tracing cost in this hot loop", the answer is a different level
  for that scope, or `OFF`.
- **The numbers.** There are none to quote, and this page types none: the
  [README's Performance section](../../README.md#performance) says what the
  benchmark suite measures and that no official figures are published yet, and
  that is where any figure will appear when one is. One copy that moves with
  the measurements is worth more than two that disagree.

## What is not captured

- **There are no published figures to rely on.** Measure the level you intend
  to run: your interpreter, your hardware, your parameter shapes (a deep
  object graph renders for longer than an `int`) and how much of your code is
  traced all move the answer.
- **A level is not a privacy control.** `ERRORS` happens to write fewer values
  because it suppresses them, but suppression and redaction are different
  mechanisms with different guarantees:
  [Keep secrets out of the logs](keep-secrets-out-of-the-logs.md) is the one
  that holds at every level.
- **Nothing here changes how much your logger writes.** Each captured event is
  still offered to the logging bridge, so the `narrativetrace` logger's own
  level is what decides log volume. Two dials.
- **A level cannot be raised retroactively.** Values not captured are gone;
  reproducing the run at `DETAIL` is the only way back, which is what the
  debugging recipe does.
- **Per-scope levels are not shown here.** This page sets one level for a
  whole run. Narrowing the traced scope instead — which objects are wrapped at
  all — is the other half of the cost question, and belongs to
  [Choosing an Integration](../choosing-an-integration.md).

**The skill for this:** `narrativetrace-doctor` — it reports the level a
project is actually running at, which is the first thing to check when a
trace is thinner than expected.
