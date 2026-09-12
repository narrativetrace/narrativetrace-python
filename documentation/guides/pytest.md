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
- **Artifacts** — on by default *(since 0.1.2, unreleased)*: each non-empty test writes a trace
  file — and, for markdown, a `.json` scenario document plus `diagrams/<Class>/<slug>.mmd` — under
  `NARRATIVETRACE_OUTPUT_DIR` (default `narrative-traces`; gitignore it, see
  [what-to-commit.md](../what-to-commit.md)). The scenario result is `PASSED` or `FAILED`. Opt out
  with `NARRATIVETRACE_OUTPUT=false` (or `output = false` in a config file, see
  [configuration.md](configuration.md)). PyPI's published `narrativetrace-pytest==0.1.1` still
  ships with it off; set `NARRATIVETRACE_OUTPUT=true` explicitly on that version.
- **Clarity footer** — the suite footer prints a `Clarity: X% high | Y% moderate | Z% low` split,
  and (when output is enabled) writes `clarity-results.json` + `clarity-report.md` with one entry
  per traced test.

> A `@pytest.mark.parametrize` id (`test_finds_it[KAYAK]`) reaches both the artifact *filename*
> and the `scenario:`/`**Scenario:**` header — never stripped or redacted. The one artifact this
> plugin writes is the value-carrying kind (see [Feature Guide](../feature-guide.md): a value-free
> structural artifact, which the cross-port naming contract titles without the parametrize id, has
> no Python counterpart yet). Keep secrets out of `parametrize` ids; see
> [Privacy and Redaction § Non-guarantees](../privacy-and-redaction.md#non-guarantees).

## Levels in tests

`NARRATIVETRACE_LEVEL=OFF` captures nothing (empty tree); an unknown value degrades to `DETAIL`
without error. The level can equally come from a config file — the environment simply wins over
one.
