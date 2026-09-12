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
  file — and, for markdown, a `.json` scenario document, `diagrams/<Class>/<slug>.mmd`, and a
  value-free `structural/<Class>/<slug>.nt` artifact *(since 0.1.2, unreleased)* — under
  `NARRATIVETRACE_OUTPUT_DIR` (default `narrative-traces`; gitignore it, see
  [what-to-commit.md](../what-to-commit.md)). The scenario result is `PASSED` or `FAILED`. Opt out
  with `NARRATIVETRACE_OUTPUT=false` (or `output = false` in a config file, see
  [configuration.md](configuration.md)). PyPI's published `narrativetrace-pytest==0.1.1` still
  ships with it off; set `NARRATIVETRACE_OUTPUT=true` explicitly on that version.
- **Structural delta + approval mode** *(since 0.1.2, unreleased)* — the `.nt` file on disk is the
  last-green baseline; the suite footer prints a `Since last green: …` summary, and a failing
  test's report prints its structural delta instead of the full trace when the shape changed. Turn
  on `NARRATIVETRACE_APPROVAL=true` to fail a test against a committed `.approved.nt` trace
  instead — see [Structural Trace Format](../structural-trace-format.md) and
  [Configuration Guide](configuration.md).
- **Clarity footer** — the suite footer prints a `Clarity: X% high | Y% moderate | Z% low` split,
  and (when output is enabled) writes `clarity-results.json` + `clarity-report.md` with one entry
  per traced test.

> A `@pytest.mark.parametrize` id (`test_finds_it[KAYAK]`) reaches the value-carrying artifact's
> *filename* and `scenario:`/`**Scenario:**` header, and `manifest.json`, exactly as before —
> never stripped or redacted. The value-free structural `.nt` artifact is the one place this *is*
> handled for you: one invocation's structural header is titled by the method and its invocation
> index, never by the parametrize id *(since 0.1.2, unreleased)* — see
> [Structural Trace Format](../structural-trace-format.md). Keep secrets out of `parametrize`
> ids regardless; see
> [Privacy and Redaction § Non-guarantees](../privacy-and-redaction.md#non-guarantees).

## Levels in tests

`NARRATIVETRACE_LEVEL=OFF` captures nothing (empty tree); an unknown value degrades to `DETAIL`
without error. The level can equally come from a config file — the environment simply wins over
one.
