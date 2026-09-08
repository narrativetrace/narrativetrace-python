# pytest plugin

`narrativetrace-pytest` registers automatically (entry point). Request the `narrative_trace`
fixture to get a fresh capture context per test.

```python
from narrativetrace import trace_object

def test_place_order(narrative_trace):
    service = trace_object(OrderService(narrative_trace), narrative_trace)
    service.place_order("cust-1", "prod-42", 3)
```

## What you get

- **Failure narratives** — a failing test prints a framed `Scenario: …` block with the indented
  execution trace, so the call path *is* the diagnosis.
- **Template warnings** — unresolved `@narrated`/`@on_error` tokens are reported once per run.
- **Artifacts** — with `NARRATIVETRACE_OUTPUT=1` (or `output = true` in a config file, see
  [configuration.md](configuration.md)), each non-empty test writes a trace file — and, for
  markdown, a `.json` scenario document plus `diagrams/<Class>/<slug>.mmd` — under
  `NARRATIVETRACE_OUTPUT_DIR`. The scenario result is `PASSED` or `FAILED`.
- **Clarity footer** — the suite footer prints a `Clarity: X% high | Y% moderate | Z% low` split,
  and (when output is enabled) writes `clarity-results.json` + `clarity-report.md` with one entry
  per traced test.

## Levels in tests

`NARRATIVETRACE_LEVEL=OFF` captures nothing (empty tree); an unknown value degrades to `DETAIL`
without error. The level can equally come from a config file — the environment simply wins over
one.
