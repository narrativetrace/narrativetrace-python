# First 10 minutes

One tiny service, one pytest test, seven steps. Every command below was run for real against this
version of the repository — the file paths, the clarity scores, and the `[REDACTED]` marker are
actual output, not illustrations. The only things that will differ on your machine are the
duration (`ms`), the random hex `trace_id`, and the three-word `trace_name` — all three generated
fresh on every run.

Python ≥ 3.12. If you have not run the demo yet, `uv run poe demo --example ecommerce --no-pause`
from the repository root is faster still — this page is for when you want to see it against *your
own* code.

## 1. Install the pytest plugin

```bash
uv add --dev narrativetrace-pytest
```

That is the entire dependency setup: the plugin pulls in the core, `narrativetrace-diagrams`, and
`narrativetrace-clarity` (step 6 below uses its console script), and registers itself with pytest
automatically through an entry point — nothing to add to `conftest.py`.

## 2. Add one service

```python
# order_service.py
class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"
```

No interface, no base class, no registration. `trace_object` wraps any concrete object directly.

## 3. Add one test

```python
# test_order_service.py
from narrativetrace import trace_object

from order_service import OrderService


class TestOrderService:
    def test_customer_places_order(self, narrative_trace):
        service = trace_object(OrderService(), narrative_trace)
        service.place_order("C-1234", "SKU-KB", 2)
```

`narrative_trace` is a fixture — request it and you get a fresh capture context, torn down (and,
with output enabled, written to disk) at the end of the test.

## 4. Run the suite

```bash
NARRATIVETRACE_OUTPUT=1 uv run pytest -s
```

```text
.Scenario: Test customer places order

Execution trace:
OrderService.place_order(customer_id: "C-1234", product_id: "SKU-KB", quantity: 2) → "ORD-C-1234-SKU-KB-2" — 0ms
Trace written: narrative-traces/traces/TestOrderService/test_customer_places_order.md


NarrativeTrace — Suite complete
  1 scenarios recorded
  Clarity: 100% high | 0% moderate | 0% low
  Reports: narrative-traces
1 passed in 1.00s
```

> The per-test "Execution trace" echo is ordinary standard output, so pytest's default capturing
> hides it unless you pass `-s` (or the test fails). The suite-footer summary always prints — it
> goes through pytest's terminal-summary hook, which bypasses capturing. See
> [Troubleshooting](troubleshooting.md#i-dont-see-the-per-test-trace-in-my-terminal).

## 5. Open the narrative

`narrative-traces/traces/TestOrderService/test_customer_places_order.md`:

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

Every value in the call flow — the parameter values, the return value — came from the call you
actually made. Nothing was written by hand. `duration_ms: 0` is real too: this call ran in under a
millisecond, and it is shown as a whole number, not hidden.

## 6. Rename `place_order` to `process` and watch clarity drop

Naming quality is measured, not asserted. The standalone scanner (the same one `poe check` wires
into this repository's own gate) reads source directly, no test run required:

```bash
uv run narrativetrace-clarity order_service.py --min-score 0.5 --max-high-issues 0 --output-dir clarity-out
```

```text
Clarity analysis complete: 1 classes scanned
Output: clarity-out
```

`clarity-out/clarity-report.md`:

```markdown
| Scenario | Score |
|----------|-------|
| OrderService | 0.89 |
```

Rename the method (definition and call site) to `process` and run the scanner again with a
threshold that would gate a real CI job:

```bash
uv run narrativetrace-clarity order_service.py --min-score 0.8 --max-high-issues 0 --output-dir clarity-out
```

```text
OrderService: overall 0.68 below --min-score 0.80
1 HIGH-severity issues exceed --max-high-issues 0
Clarity analysis complete: 1 classes scanned
Output: clarity-out
```

The command now exits `1`. `clarity-out/clarity-report.md` shows exactly why:

```markdown
### OrderService

## Scores

| Category | Score | Weight | Weighted |
|----------|-------|--------|----------|
| Method Names | 0.10 | 0.30 | 0.03 |
| Class Names | 0.91 | 0.20 | 0.18 |
| Parameter Names | 0.92 | 0.25 | 0.23 |
| Structural | 1.00 | 0.15 | 0.15 |
| Cohesion | 0.90 | 0.10 | 0.09 |
| **Overall** | **0.68** | | |

| Severity | Category | Element | Suggestion |
|----------|----------|---------|------------|
| HIGH | method-name | `OrderService.process` | Use a domain-specific verb+noun (e.g., calculateTotal, reserveInventory) |
```

Same call, same values, same everything but the name — the overall score fell from 0.89 to 0.68,
the method-name dimension alone fell from 0.81 to 0.10, and a HIGH-severity issue appeared with a
concrete suggestion. See the [Clarity Guide](guides/clarity.md) for the full scoring model. Rename
it back to `place_order` (or to something even more specific) before continuing.

## 7. Add `@not_traced` and see redaction

```python
from narrativetrace import not_traced, trace_object


class OrderService:
    @not_traced("payment_token")
    def place_order(self, customer_id, product_id, quantity, payment_token):
        return f"ORD-{customer_id}-{product_id}-{quantity}"
```

Pass a token in the test (`service.place_order("C-1234", "SKU-KB", 2, "tok_live_51H8x9J")`) and run
again. The trace:

```text
- **OrderService.place_order**(customer_id: `"C-1234"`, product_id: `"SKU-KB"`, quantity: `2`, payment_token: `[REDACTED]`) → `"ORD-C-1234-SKU-KB-2"` — 0ms
```

The parameter name still appears — you can see a token *was* passed — but its value never reaches
disk. See [Privacy and Redaction](privacy-and-redaction.md) for what else redaction covers and the
one documented way it can be narrowed.

## Where to go next

| You want | Go to |
|---|---|
| A different integration path than the pytest fixture above | [Choosing an Integration](choosing-an-integration.md) |
| The row-by-row privacy contract | [Privacy and Redaction](privacy-and-redaction.md) |
| Which generated files to commit | [What to Commit](what-to-commit.md) |
| Something above did not work as shown | [Troubleshooting](troubleshooting.md) |
| Every configuration knob | [Configuration Guide](guides/configuration.md) |
