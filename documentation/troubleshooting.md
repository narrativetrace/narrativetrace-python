# Troubleshooting

Symptom → cause → fix, for the failure modes people actually hit. Some entries are the full
explanation; others point at the guide that already carries it in more detail rather than
repeating it here — one home per fact.

## No trace output files

**Cause:** artifact output is on by default, so something turned it off — an
`NARRATIVETRACE_OUTPUT=false` in the environment or CI, or `output = false` in `narrativetrace.toml` /
`pyproject.toml`'s `[tool.narrativetrace]` — or the files are in a directory you are not looking in.

**Fix:** remove the opt-out, and check `NARRATIVETRACE_OUTPUT_DIR` (default `narrative-traces/` under
the pytest rootdir) — see the [Configuration Guide](guides/configuration.md). An empty trace (a
wrapped object whose methods were never called) writes nothing even with output enabled; there is
no empty file to find.

## I don't see the per-test trace in my terminal

**Cause:** the per-test "Execution trace" echo is written with a plain `print()`, and pytest
captures standard output by default — a plain `pytest` run shows nothing on your terminal even
though the file under `narrative-traces/` was written correctly.

**Fix:** run with `-s` (`pytest -s`) to see it live, or check the file directly. The suite-footer
summary (`NarrativeTrace — Suite complete …`) always prints regardless, because it goes through
pytest's `pytest_terminal_summary` hook, which bypasses capturing.

## A `*args` method's parameters show as one `args: [...]` value

**Cause:** `inspect.signature` can bind parameter names for an ordinary signature, but a method
that takes `*args` has no per-argument names to read — there is nothing named to reconstruct that
Python itself does not have.

**Fix:** add `@traced("first", "second", ...)` to supply the names explicitly:

```python
from narrativetrace import traced

class Calc:
    @traced("a", "b")
    def add(self, *args):
        return sum(args)
```

## `trace_object` wraps it, but calls still aren't traced

**Cause:** you have a reference to the *original*, unwrapped object somewhere — `trace_object`
returns a new wrapper; the object you passed in is untouched. A call made on that original
reference, or on `self` from inside an untraced method, bypasses the wrapper entirely.

**Fix:** make sure every caller holds the object `trace_object(...)` returned, not the one you
constructed. This usually means wrapping once, at a composition root or a fixture, and passing the
wrapped reference everywhere downstream.

## Cross-thread or cross-task traces are empty, or a forked child shows up as a new root

**Cause:** `ContextVarNarrativeContext` isolates threads *and* asyncio tasks by design — work
submitted to a thread pool or spawned as a task only joins the parent trace if it received a
context snapshot, or went through `ForkJoinGroup`/`FireAndForgetGroup`. A worker that never got
either records into its own, separate context. Separately: forking directly inside an `async def`
traced method resolves the parent through the *synchronous* call stack, which is empty inside a
coroutine, so children launched that way land as siblings/roots rather than nested under the
`async` caller — a known, open gap.

**Fix:** take an explicit snapshot at the boundary, or use `ForkJoinGroup.create(...)` /
`FireAndForgetGroup.create(...)` from a synchronous method (or a thread-pool-backed one) rather
than directly inside `async def`. If you only need the forked work's own trace, call
`capture_trace()` inside the task, on the thread or task that recorded it.

## Clarity score seems wrong

**Cause:** usually a generic name the scorer flags — `get`, `set`, `process`, `handle`, `data`,
`info`, `temp` and similar score low regardless of context; a name your team accepts as domain
vocabulary but the built-in dictionaries do not know scores as unknown, not as domain-specific.

**Fix:** review the issues list in `clarity-report.md` and either rename (`getData()` →
`fetchOrderHistory()`), or teach the scorer your vocabulary through a committed `glossary.json` —
see the [Clarity Guide](guides/clarity.md#your-own-vocabulary-from-the-glossary-you-already-have).

## `DuplicateConfigurationError` on startup

**Cause:** the same directory has both a `narrativetrace.toml` and a `pyproject.toml` with a
`[tool.narrativetrace]` table. Configuration resolution refuses to silently pick one.

**Fix:** keep exactly one config source per directory — delete or merge one of the two. See the
[Configuration Guide](guides/configuration.md#where-settings-come-from).

## ASGI middleware isn't capturing a route I expected it to skip, or skipping one I expected captured

**Cause:** `excluded_paths` matches the request path by exact string, not a glob or prefix —
excluding `/health` does not exclude `/health/live`, and only HTTP scopes are ever captured
(WebSocket and lifespan scopes always pass through untouched).

**Fix:** list every path you want excluded explicitly, or match earlier in your own routing layer
before the middleware runs. See the [FastAPI/ASGI Guide](guides/fastapi-asgi.md).

## A value I expected to be redacted appears in a trace

**Cause:** the deny-list matches on the *field or parameter name*, not blanket "everything named
`data`" — a value stored under a name the deny-list does not recognize (and that does not look
like a JWT, card number, `Set-Cookie` string, or national identity number by shape) is not
redacted by default. Separately: a
`{param.path}` narration template always checks the *default* deny-list, even if the surrounding
`ValueRenderer` was built with a custom or disabled `RedactionPolicy` for plain parameter
rendering — a documented narrowness, not a bug.

**Fix:** mark the member explicitly with `@not_traced(...)` / `not_traced_field(...)` — an explicit
annotation always wins, regardless of policy. See
[Privacy and Redaction](privacy-and-redaction.md) for the full, verified contract.
