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

## Output settings (pytest plugin)

| Key | Environment variable | Meaning | Default |
|---|---|---|---|
| `output` | `NARRATIVETRACE_OUTPUT` | truthy → write per-test artifacts | on |
| `output_dir` | `NARRATIVETRACE_OUTPUT_DIR` | artifact directory | `narrative-traces` |
| `format` | `NARRATIVETRACE_FORMAT` | `markdown` / `text` / `mermaid` / `plantuml` | `markdown` |
| `level` | `NARRATIVETRACE_LEVEL` | capture level for the fixture's context | `DETAIL` |
| `glossary_dir` | `NARRATIVETRACE_GLOSSARY_DIR` | directory holding the committed `glossary.json`, read as the vocabulary clarity scores with ([guides/clarity.md](clarity.md)) | working directory |
| `canonical` | `NARRATIVETRACE_CANONICAL` | also write the per-test `<test>.canonical.json` entry array | `false` |

`output` is on by default: the `narrative_trace` fixture writes every non-empty test's artifacts
under `narrative-traces/` without any configuration at all. Opt out with
`NARRATIVETRACE_OUTPUT=false` (`0`/`no`/`off` all work too, case-insensitively) or `output = false`
in a config file — see [what-to-commit.md](../what-to-commit.md) for gitignoring the directory.

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

## Service identity

Stamp service metadata onto every span for correlation:

```python
from narrativetrace import ServiceIdentity

context = ContextVarNarrativeContext(service_identity=ServiceIdentity("orders", "1.4.0", "prod"))
```
