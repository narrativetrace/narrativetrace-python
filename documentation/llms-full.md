# narrativetrace-python — full reference

Zero-boilerplate execution tracing where your method and parameter names are the log. A uv
workspace: a dependency-free core plus thin integration packages.

## Core concept

`trace_object(obj, context)` returns a transparent wrapper; calling its methods appends immutable
`TraceEvent`s to the context. `context.capture_trace()` builds an immutable `TraceTree` that
renderers, exporters, and the clarity analyzer consume. No logging calls appear in business code.

```python
from narrativetrace import ContextVarNarrativeContext, MarkdownRenderer, trace_object

context = ContextVarNarrativeContext()
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)
print(MarkdownRenderer().render(context.capture_trace()))
```

## Core API (`narrativetrace`)

- **Capture:** `NarrativeContext` (ABC), `ContextVarNarrativeContext` (default; contextvars per
  instance, isolates threads + asyncio), `NoopNarrativeContext`, `NOOP_CONTEXT`. Key methods:
  `enter_method`, `exit_method_with_return`, `exit_method_with_exception`, `capture_trace`,
  `reset` (per-scope), `snapshot`, `trace_loss`, `set_request_context`, `set_user_context`,
  `adopt_trace_id`, `trace_id`, `story_id`, `chapter_id`.
- **Capture scope — what `capture_trace()` reports.** Its own spans, plus everything published to
  it *transitively*: spans handed over by workers whose snapshot scope has closed, and the
  reportable set of every worker whose scope is still open (so a call is visible from the moment
  it is published, not from the moment its scope closes). A two-hop chain — origin → worker →
  grandchild — reaches the origin whole. Work on a thread that never activated a snapshot stays
  out; an asyncio task started inside a traced call inherits its creator's stack, so its work is
  the creator's work without any propagation. Placement follows *submit* time: submitted while the
  parent span is open → child of it; submitted after the parent returned → next root of the trace.
- **Propagation:** `context.snapshot()` → `ContextSnapshot.activate()` (or `.wrap(fn)`) on the
  worker; `activate_without_adoption()` for helpers that publish their children themselves. The
  origin stack is held weakly, both ledgers are capped at 10,000 spans, an over-cap hand-over is
  refused *whole*, and refusals are reported through `TraceLoss` (`dropped_events`,
  `refused_scopes`, `refused_spans`) — one suite-footer line, omitted at zero loss.
- **Wrapping / decorators:** `trace_object`, `@narrated("… {param} …")`, `@on_error(Exc, "…")`
  (stackable), `@not_traced("param")`, `not_traced_field(...)`, class attr `__nt_not_traced__`.
- **Levels:** `TracingLevel` (`OFF`/`ERRORS`/`SUMMARY`/`NARRATIVE`/`DETAIL`),
  `NarrativeTraceConfig`, `NarrativeTraceConfig.resolve()` (unknown → DETAIL).
- **Configuration:** `ConfigResolver` — `NARRATIVETRACE_<KEY>` env → `narrativetrace.toml` →
  `pyproject.toml [tool.narrativetrace]` → default, discovered by walking up from the cwd. Two
  sources in one directory raises `DuplicateConfigurationError`.
- **Model:** `TraceTree`, `TraceNode`, `MethodSignature`, `ParameterCapture`, `SpanContext`,
  `TraceId`/`SpanId`, `TraceOutcome` = `Returned`/`Threw`/`Incomplete`, `RenderedValue` =
  `StringVal`/`IntVal`/`FloatVal`/`BoolVal`/`InstantVal`/`ObjectVal`/`ListVal`/`NullVal`.
- **Rendering:** `MarkdownRenderer`, `ProseRenderer`, `IndentedTextRenderer`, `ValueRenderer`,
  `FrontmatterBuilder`, `TraceMetadata`.
- **Redaction:** `RedactionPolicy`, `REDACTED_MARKER`.
- **Concurrency:** `ForkJoinGroup` / `FireAndForgetGroup` — `create(context[, name])`,
  `run_async(lambda: coro)`, `wrap(fn)` (thread pools), `merge()`. Children inherit full trace
  identity (trace id, service, level, request/user metadata) and are tagged with `ConcurrencyInfo`
  (`group_id`, `kind`, thread or `task_label`). `ConcurrencyKind` is `FORK_JOIN`,
  `FIRE_AND_FORGET` or `ASYNC` — the last stamped on the first span a thread or task opens under
  an activated snapshot, keyed by the launching span, so a renderer can group raced siblings
  instead of pinning the scheduler's dispatch order.
- **Export:** `export_json(tree)`, `export_document_json(tree, metadata)` (nested event stream,
  `chapter-tree.schema.json`), `export_chapter_json(tree, metadata)` (`chapter.schema.json`),
  `tree_canonical.export_canonical_entries(tree)` (flat entry array, `entry.schema.json`). One
  `canonical.SCHEMA_VERSION` (`"1.2"`) stamps all three plus the OTel attributes.
  `TraceMetadata(scenario, result)` takes a `ScenarioResult`: `wire_name` (`success`/`error`) goes
  into JSON, `display_name` (`PASSED`/`FAILED`) into the Markdown caption. Schemas live in
  `schema/`, copied byte-identically from the shared master copy.
- **Trace identity:** resolved once per `TraceTree` (adopt the capturing context's id → inherit the
  first span context anywhere in the tree → generate a W3C id) and read by every exporter through
  `identity.resolve_identity(tree)`, so a chapter and its `.canonical.json` always name the same
  trace. `nt.storyId` falls back to the first root call (`Class.method`, else `unknown`),
  `nt.chapterId` to the story, `nt.traceName` to the resolved id. An empty tree carries no id.
  The nested document's `trace` block is the one exception — still omitted without a span
  (cross-runtime format decision, tracked in the private backlog).
- **Logging:** `LoggingTraceConsumer`, `NarrativeContextFilter`, `request_log_scope(keys)`,
  `current_scope_keys()`.
- **Identity/metadata:** `ServiceIdentity`, `HttpRoute`, `ClientIp`, `EnduserId`, `SessionId`,
  `TenantId`.

## Integrations

- **`narrativetrace-pytest`** — `narrative_trace` fixture (fresh context per test), failure
  narratives, template warnings, artifacts (`NARRATIVETRACE_OUTPUT`/`_OUTPUT_DIR`/`_FORMAT`),
  suite footer clarity split, per-suite `clarity-results.json` + `clarity-report.md`. Also writes
  a value-free `.nt` structural artifact per invocation plus `manifest.json`, with a last-green
  delta on the suite footer and a failing test's report; `NARRATIVETRACE_APPROVAL=true` fails a
  test against a committed `.approved.nt` trace instead, promoted via `poe approve` /
  `narrativetrace-approve`.
- **`narrativetrace-diagrams`** — `MermaidSequenceDiagramRenderer`,
  `PlantUmlSequenceDiagramRenderer` (Java-exact tokens; control-char folding on interpolated
  values).
- **`narrativetrace-otel`** — `OtelTraceEventListener` (live, span per enter/exit anchored to
  event timestamps, `PerishableMap` orphan eviction), `TraceSpanExporter` (batch, nested spans,
  `narrative.duration_ms`, concurrency + `nt.*` attrs), `attributes` mapper (typed structured
  flattening depth 3, homogeneous arrays, string-inference fallback).
- **`narrativetrace-asgi`** — `NarrativeTraceMiddleware` (pure ASGI; fail-safe; finally-export
  with real status + duration; empty-tree skip; `excluded_paths`), `get_narrative_context()`,
  `parse_traceparent`/`format_traceparent`/`Traceparent`, `attach_traceparent[_async]`,
  `RequestContext`, `UserContext`, `RequestExporter`.
- **`narrativetrace-clarity`** — `analyze(tree, vocabulary=EMPTY) -> ClarityResult`
  (`overall_score`, per-dimension scores, ranked `issues`), `export(entries)`,
  `render_suite_report(entries)`, `render`, `Severity`, `DomainVocabulary`/`EMPTY`,
  `scanner.scan_paths/scan_source`, `cli:main`. Weights 0.30/0.20/0.25/0.15/0.10; empty-tree
  envelope 0.47. Console script `narrativetrace-clarity` gates CI.
  `vocabulary` is the project's own words, read from the committed `glossary.json` (ADR-012) by
  `narrativetrace_glossary.read_project_vocabulary(dir)`: a `verb-phrase` term contributes its
  leading verb as a domain verb and the rest as domain nouns, and `word`/`noun-phrase` terms
  contribute every token as a domain noun. Accepted shorthand comes only from the glossary's
  root-level `abbreviations` map (`{"fx": "foreign exchange"}`, schema 2) — never from the tokens
  of a committed term, so `calc total` does not accept `calc`. Built-in tiers keep
  authority (generic verbs, boolean prefixes and meaningless placeholders are never promoted;
  deprecated synonyms, `template` entries and `stale` terms are never vocabulary), and only the
  *committed* file counts. The pytest plugin reads it once per session from
  `narrativetrace.glossary_dir`.
- **`narrativetrace-structlog`** — `narrative_context_processor` (same keys as the stdlib filter).

## Divergences (pinned)

- `PerishableMap` re-put at capacity evicts nothing (predictable contract).
- `RenderedValue.LongVal→IntVal`, `DoubleVal→FloatVal`, `BooleanVal→BoolVal` (unbounded ints).
- Logging level: enter/return at DEBUG (Java TRACE has no stdlib analog).
- W3C traceparent adopt/inject is TS-ahead parity (Java mints a fresh id per request).
- Clarity scanner is class-only (matches Java reflection; skips underscore-private).

## Examples

`examples/ecommerce` (concurrency), `examples/minecraft` (naming pair), `examples/hotel_booking`
(clarity HIGH), `examples/fastapi_service` (ASGI) — each with characterization tests.
