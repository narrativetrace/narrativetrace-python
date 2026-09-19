# Configuration

## Where settings come from

Every setting is resolved through one chain. The first source that has the
key wins:

1. **Environment** — `NARRATIVETRACE_<KEY>` (the key upper-cased, so
   `output_dir` reads `NARRATIVETRACE_OUTPUT_DIR`)
2. **`narrativetrace.toml`** — keys at the document root
3. **`pyproject.toml`** — keys under `[tool.narrativetrace]`
4. **Built-in default**

Config files are found by walking up from the working directory. The
nearest directory holding either file wins, and the walk stops there.

**Two config sources in one directory is a hard error.** If a directory has
both a `narrativetrace.toml` and a `pyproject.toml` with a
`[tool.narrativetrace]` table, resolution raises
`DuplicateConfigurationError` rather than silently picking one. A malformed
file still counts as a declared source — a broken config should fail loudly,
not lose a coin toss.

```toml
# narrativetrace.toml
level = "NARRATIVE"
output = true
output_dir = "narrative-traces"
format = "markdown"
```

```toml
# ...or in pyproject.toml — never both in the same directory
[tool.narrativetrace]
level = "NARRATIVE"
output = true
```

```bash
# Environment always wins, for one-off overrides
export NARRATIVETRACE_LEVEL=OFF
```

## Tracing level

Capture is gated by a tracing level, checked *before* any rendering happens.
Levels are cumulative — each includes everything below it.

| Level | Captures |
|---|---|
| `OFF` | nothing (wrappers short-circuit; the cheapest possible path) |
| `ERRORS` | only the paths that ended in an error or never completed |
| `SUMMARY` | entry points plus their leaf and error calls, intermediate frames collapsed |
| `NARRATIVE` | the full call structure with resolved `@narrated` prose |
| `DETAIL` | + parameter and return values (default) |

Parameter values are dropped **at capture time** below `DETAIL`, so they
cannot be recovered later from a lower-level trace. `ERRORS` and `SUMMARY`
additionally prune the tree after capture.

Set it in code, in a config file, or via the environment:

```python
from narrativetrace import ContextVarNarrativeContext, NarrativeTraceConfig, TracingLevel

context = ContextVarNarrativeContext(NarrativeTraceConfig(level=TracingLevel.NARRATIVE))
```

`NarrativeTraceConfig.resolve()` runs the chain above for the `level` key.
Unknown or empty values degrade to the default rather than raising —
misconfiguration must never take capture down with it. Level names are
case-insensitive.

## Two dials, two paths

**I set the tracing level to `DETAIL` but nothing shows up in my logs. Or: I set my logger to
`WARNING` and the trace still appears in my pytest artifacts. Which setting wins?**

Both, because they answer different questions. NarrativeTrace has two dials, and getting a
captured trace into your logger is a separate step from capturing it at all.

**Dial 1, the tracing level, decides what is captured.** `OFF`, `ERRORS`, `SUMMARY`, `NARRATIVE`,
`DETAIL` — cumulative, each including everything below it (the table above). It is
NarrativeTrace's own setting, and it acts at two different points, not one: at `OFF`,
`context.is_active()` is `False` and `trace_object`'s wrapper skips interception entirely — the
wrapped call runs with none of the capture machinery touched, and nothing becomes an event, for
any consumer. From `ERRORS` up, every call *is* intercepted and recorded — `ERRORS` and `SUMMARY`
don't skip interception, they prune the resulting tree *after* capture (dropping non-error paths,
collapsing intermediate frames); only below `DETAIL` are parameter values left out at capture
time, unrecoverable later regardless of what the logger does. No other setting can bring back what
`OFF` skipped or `DETAIL` alone captures.

**Dial 2, your logger's level, decides what is printed — once a trace reaches your logger at
all.** By default, nothing does: NarrativeTrace writes nothing to `logging.getLogger
("narrativetrace")` (the logger name `LoggingTraceConsumer` targets) unless you send a trace
there yourself. When you do, each kind of line has its own default level: an entry and a return at
`DEBUG` (Python's stdlib `logging` has no `TRACE` level to mirror Java's), an exception at
`WARNING` as `!! {type}: {message} [{error_context}]`. Your logger's threshold then does what it
always does — raising it silences lines. It never captures more, and it never captures less.

**Now the two paths, which is where the confusion comes from.** The captured trace — everything
`capture_trace()` returns, and everything downstream of it: the pytest plugin's per-test
artifacts, the `.nt` approval baseline, the clarity report, `TraceSpanExporter`'s batch
OpenTelemetry export, the rendered narrative — is written straight into the context's own event
store the moment each method enters and exits. That write never consults your logger, in either
direction: a `CRITICAL`-level `narrativetrace` logger doesn't shrink it, and no logger at all
doesn't either.

Sending a captured trace to your logger is a separate, explicit step, through
`LoggingTraceConsumer`, and there are two ways to take it:

- **Replay after capture** — `export_to_logger(trace)` sends an already-finished `TraceTree`
  through a private `LoggingTraceConsumer` in one call. This is the path the [60-second
  tutorial](../sixty-seconds.md#send-it-to-your-logger) and every guide in this repository use.
- **Live, as events happen** — attach a `LoggingTraceConsumer` as the synchronous listener of a
  `DualPathPipeline` you assemble yourself, typically alongside a `BufferedEventConsumer` as its
  best-effort path (a bounded ring, 65,536 events by default, load-shedding under pressure, every
  loss counted — see [Concurrency](../../README.md#concurrency)) for any other live consumer, an
  `OtelTraceEventListener` included, fed from the same event stream.

Either way, the log line and the trace artifact are two independent readers of the same captured
events. Raising `narrativetrace`'s logger level silences log lines; it can't touch
`capture_trace()`'s output, because that output never passed through the logger in the first
place.

**Where each dial lives.**

| Dial | Where it lives |
|---|---|
| Tracing level | `NARRATIVETRACE_LEVEL` env var; `level` in `narrativetrace.toml` or `[tool.narrativetrace]` in `pyproject.toml`; `NarrativeTraceConfig(level=TracingLevel.X)` in code |
| Logger threshold | Ordinary `logging` config on `logging.getLogger("narrativetrace")` — the name `LoggingTraceConsumer` targets by default |
| Level per kind of line | `LoggingTraceConsumer(levels={EventType.ENTRY: ..., EventType.RETURN: ..., EventType.EXCEPTION: ...})`, or the same `levels=` argument passed through `export_to_logger(trace, levels=...)` |

**Rules of thumb.** To reduce log volume, raise `narrativetrace`'s logger threshold; the captured
trace is untouched. To reduce the size of the trace, lower the tracing level — `ERRORS`/`SUMMARY`
prune it after capture. To reduce overhead, drop the tracing level to `OFF`: that's the only step
that skips interception itself; `ERRORS`, `SUMMARY` and `NARRATIVE` still intercept and record
every call the same way `DETAIL` does, they just render fewer values and prune more afterward. The
logger threshold changes nothing about capture cost, at any level. To keep tracing on in
production but out of the logs, leave the tracing level at `SUMMARY` or above and either don't
send traces to your logger at all, or send them and set `narrativetrace`'s logger to `WARNING`:
either way, `capture_trace()` and everything downstream of it stay complete.

## Output settings (pytest plugin)

| Key | Environment variable | Meaning | Default |
|---|---|---|---|
| `output` | `NARRATIVETRACE_OUTPUT` | truthy → write per-test artifacts | on *(since 0.1.2)* |
| `output_dir` | `NARRATIVETRACE_OUTPUT_DIR` | artifact directory | `narrative-traces` |
| `format` | `NARRATIVETRACE_FORMAT` | `markdown` / `text` / `mermaid` / `plantuml` | `markdown` |
| `level` | `NARRATIVETRACE_LEVEL` | capture level for the fixture's context | `DETAIL` |
| `glossary_dir` | `NARRATIVETRACE_GLOSSARY_DIR` | directory holding the committed `glossary.json`, read as the vocabulary clarity scores with ([guides/clarity.md](clarity.md)) | working directory |
| `canonical` | `NARRATIVETRACE_CANONICAL` | also write the per-test `<test>.canonical.json` entry array | `false` |
| `approval` | `NARRATIVETRACE_APPROVAL` | truthy → verify structure against a committed approved trace *(since 0.1.2)* | `false` |
| `approved_dir` | `NARRATIVETRACE_APPROVED_DIR` | directory holding committed `*.approved.nt` traces *(since 0.1.2)* | `test-narratives` |

`output` is on by default *(since 0.1.2)* — PyPI's published `0.1.1` still ships it
off: the `narrative_trace` fixture writes every non-empty test's artifacts under
`narrative-traces/` without any configuration at all. Opt out with `NARRATIVETRACE_OUTPUT=false`
(`0`/`no`/`off` all work too, case-insensitively) or `output = false` in a config file — see
[what-to-commit.md](../what-to-commit.md) for gitignoring the directory.

`glossary_dir` is read whether or not a glossary exists: reading changes
nothing on disk, so it needs no opt-in, and a repository without the file
scores with the built-in dictionaries alone.

Format names are matched case-insensitively. Only `markdown` writes the
coupled companions (a sibling `.json` canonical export and a Mermaid
`.mmd`); `text`, `mermaid`, and `plantuml` replace the Markdown trace with
that single artifact.

`canonical` is independent of `format`: a run that chose `text` or `mermaid`
for its human artifact still owes a conformance runner its entries. The file is
a flat JSON array of canonical entries at schema `1.2`, one `method_enter` and
one `method_exit` per traced call, each valid against `entry.schema.json`. It is
off by default because it is a machine artifact — for other runtimes, conformance
fixtures and translation — not something to read after a failure.

## Structural artifact and approval mode

*(since 0.1.2)*

The Markdown path additionally writes a value-free `.nt` structural artifact beside the
narrative — see [Structural Trace Format](../structural-trace-format.md) for the grammar.
The file on disk is the **last-green baseline**: a green run advances it, a non-green run
compares against it but never overwrites it, so every delta reads "what changed since the
last time this scenario passed". "Green" is the whole verdict, not just the assertions — a
test that passed but whose structure approval mode *rejected* ends non-green, and its
structure is not written. Rejecting a change therefore leaves the baseline where it was,
and reverting the change reports no delta.

`approval` turns on approval mode: after a **passing** test, the scenario's value-free
structure is verified against the committed baseline
`<approved_dir>/<TestClassName>/<slug>.approved.nt`. A missing baseline or a structural
difference fails the test with a readable diff and writes the current structure beside the
baseline as `*.received.nt`. Review it, then promote with `uv run poe approve` (or the
`narrativetrace-approve` console script, which reads this same `approved_dir` key). Failing
tests are never verified — approval only judges a test that would otherwise have passed.

Every run also writes `<output_dir>/manifest.json`: a top-level `run` object (`id`, `name` —
the run's own three-word phrase, *(since 0.1.2)*, see [The run has a
name](#the-run-has-a-name) below) followed by one row per traced scenario, naming its
test, its invocation number when the method ran more than once, and every artifact it owns:

```json
{
  "schema": "narrativetrace/scenario-manifest/1",
  "run": {
    "id": "a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4",
    "name": "bold elk soars"
  },
  "scenarios": [
    {
      "scenario": "find TENT",
      "testClass": "CatalogTest",
      "testMethod": "test_finds_it",
      "invocation": 2,
      "artifacts": {
        "trace": "traces/CatalogTest/test_finds_it-002-tent.md",
        "structural": "structural/CatalogTest/test_finds_it-002-tent.nt"
      }
    }
  ]
}
```

The suite footer prints one more line summarizing every scenario's structural status:

```
NarrativeTrace — Suite complete
  run: bold elk soars
  2 scenarios recorded
  Clarity: 100% high | 0% moderate | 0% low
  Reports: narrative-traces
  Since last green: 1 scenario unchanged · 1 changed: "Customer places order" (+1 call InventoryService.release)
```

A failing test's console report prints the structural delta against the last-green
artifact instead of the full trace, when the structure actually changed.

### The run has a name

*(since 0.1.2)* One run id is generated per pytest session — the plugin's own
`pytest_sessionstart` hook, a W3C-shaped id, never a shared constant — and its three-word
phrase (the same namer a trace id's name comes from) is the **run name**. It appears in:

- the console suite footer (`run: bold elk soars`, above);
- `manifest.json`'s top-level `run` object (`id` and `name`, above);
- the YAML frontmatter of every Markdown trace document (`run: bold elk soars`, alongside
  `scenario:`);
- the stdlib logging bridge's MDC-analog context as `runName` for the whole session (see
  [Logging Guide](logging.md)), so one grep finds one run's log lines.

The run name and its id are invariant-protected the same way a trace's own name is: they
**never** reach the structural `.nt` text, an approved or received trace, an artifact
filename, or the manifest's per-scenario keys — running the identical suite twice, with two
different run names, produces byte-identical `.nt` files and delta output every time. A
trace's own name (`trace: bold elk soars (a1b2c3d)` in the console/indented renderer, `The
trace bold elk soars:` in prose, the phrase in the Markdown title line) is a *different*
thing — one per trace, not one per run — and is equally absent from the `.nt` text.

## Service identity

Stamp service metadata onto every span for correlation:

```python
from narrativetrace import ServiceIdentity

context = ContextVarNarrativeContext(service_identity=ServiceIdentity("orders", "1.4.0", "prod"))
```
