# NarrativeTrace Feature Guide (Python)

What NarrativeTrace for Python ships, from a user's perspective. For the
full cross-platform feature catalog (all tiers, all platforms), see the
canonical feature guide:
<https://github.com/narrativetrace/narrativetrace-java/blob/main/documentation/feature-guide.md>.

**Status labels** (same vocabulary as the canonical guide):

- **Free** — shipped and available in this repository, under the Business
  Source License 1.1 (see *Licensing* below).
- **Pro** — shipped in NarrativeTrace Pro (commercial tier, a separate
  distribution).
- **In development** — actively being built; the design is settled.
- **Planned** — specified, not yet started; may change.

**Licensing.** NarrativeTrace's API and output format are open standards
(Apache 2.0). Its runtime is free and source-available (BSL 1.1, converting to
Apache 2.0 four years after each release). Pro is commercial. Everything marked
**Free** here is that runtime: free to use in production, source-available, not
open source — the root [`LICENSE`](../LICENSE) is the authority.

Per-topic documentation lives under [guides/](guides/). The *why* behind the Python-specific
mechanisms — rejected alternatives included — is recorded as an internal decision log, not
published here.

---

## Capture the story of your code (core tracing)

| Feature | Status | Notes |
|---|---|---|
| Automatic narrative capture — method, class, parameter names, return values, timing, errors; zero log statements | Free | `trace_object(obj, context)` + `ContextVarNarrativeContext`; names read via `inspect.signature` |
| Enrichment decorators — `@narrated("… {param} …")`, stackable `@on_error(ExcType, "…")` (most-specific wins), `@traced` name overrides for `*args`, `@narrative_summary` | Free | [guides/decorators.md](guides/decorators.md) |
| Sensitive data redaction — `@not_traced` parameters, `not_traced_field(...)` / `__nt_not_traced__` fields, name-pattern redaction (`RedactionPolicy`) | Free | Redacted values render as `[REDACTED]`, never read at all for marked members; a `@narrated`/`@on_error` template path reaching a redacted member resolves to the same marker, at every depth of the path; a `NamedTuple` is introspected by field name rather than printed as an anonymous positional collection, so a redacted field stays hidden one container deep too |
| Five capture levels (OFF → ERRORS → SUMMARY → NARRATIVE → DETAIL), changeable at runtime, `NARRATIVETRACE_LEVEL` env channel | Free | Level names differ from the Java runtime's (SUMMARY/NARRATIVE vs NARRATIVE/FLOW). Parameter values exist only at DETAIL; suppression happens at capture, not at render |
| Two-gate levels — capture level and log level are independent | Free | [guides/configuration.md](guides/configuration.md) |
| Concurrency capture — `ForkJoinGroup` / `FireAndForgetGroup` over asyncio tasks *and* `ThreadPoolExecutor`, full-identity snapshot propagation, cross-task grafting | Free | The story stays coherent when execution isn't sequential |
| Bidirectional propagation — a snapshot carries the trace *into* a thread or task, and the work traced there comes *back*: the capturing stack reports it from the moment it is published, transitively through a chain of async hops | Free | Placement follows submit time; adopted work is tagged `ConcurrencyKind.ASYNC`; helpers that re-emit their own children opt out with `activate_without_adoption()`; bounded at 10,000 spans per stack, over-cap hand-overs refused whole and reported through `TraceLoss` |
| Trace identity — trace id, human-readable trace names, story/chapter id derivation | Free | Canonical-schema aligned |
| Purity contract — introspection enumerates stored data; `@property` getters never run; every invoked member is bounded and exception-isolated | Free | [guides/decorators.md](guides/decorators.md) |
| Fail-safe capture — a throwing renderer or exporter never masks the business result or exception (sync and `async` methods) | Free | |

## Attach it to your stack (integrations)

| Feature | Status | Notes |
|---|---|---|
| Explicit object wrapping — `trace_object(...)` | Free | No import hooks, no monkey-patching; see the platform ADL |
| pytest plugin — `narrative_trace` fixture, failure narratives, template warnings, per-test artifacts, suite summary | Free | Auto-registers via entry point; [guides/pytest.md](guides/pytest.md) |
| ASGI middleware (Starlette/FastAPI) — request-boundary capture/export, request + user metadata, excluded paths, W3C `traceparent` adoption | Free | [guides/fastapi-asgi.md](guides/fastapi-asgi.md) |
| Request-scoped context accessor — `get_narrative_context()` (usable as a FastAPI `Depends`) | Free | |
| Outbound `traceparent` injection for `httpx` (sync + async hooks) | Free | Python-only extra; closes the cross-service loop |
| WSGI (Flask) middleware | Planned (Free) | Same request-boundary contract as ASGI |
| Django middleware | Planned (Free) | Same request-boundary contract as ASGI |

ASGI is the only shipped web integration today — Flask/WSGI and Django
are Planned, not merely undocumented.

## Read the story (outputs)

| Feature | Status | Notes |
|---|---|---|
| Indented text, Markdown, and prose renderers | Free | |
| Trace value references — content-addressed dedup of repeated captured values with readable labels (`‹Hotel›=full` on first emission, `‹Hotel›` after) | Free | `render.value_reference.ValueReferenceIndex` via `MarkdownRenderer`. Labels come from the structured value's identity field (name/id/description/…), never a redacted one; byte equality certifies sameness; containment inside other captured values counts and is replaced. Markdown only |
| Intra-trace value deltas — a re-capture of the same entity, changed, renders as a diff against the reference (`‹Dinner›′{amount: 100.0→92.0, currency: "USD"→"EUR"}`) | Free | `render.value_delta.value_delta`. "Same entity" is the same structured type name plus an equal identity field; changed scalar fields only (`StringVal`/`IntVal`/`FloatVal`/`BoolVal`/`InstantVal`/`NullVal`), never reconstructed from the structured tree. A changed nested object or list, a different field set, or a value with no identity field renders in full exactly as before. A changed variant that itself repeats is defined AS the diff (`‹Dinner·2›=‹Dinner›′{…}`). Markdown only |
| Per-test trace files with `.json` and Mermaid `.mmd` companions | Free | `NARRATIVETRACE_OUTPUT=1`; empty traces write nothing |
| Canonical JSON export (event-stream form) | Free | `export_json` / `export_document_json`; round-trip tested, and schema-validated against `chapter-tree.schema.json` from the bytes the real writer put on disk |
| Per-service chapter schema (`nt.entryType` / `schemaVersion` / story-chapter entries) | Free | `export_chapter_json`; validated against `chapter.schema.json`. Correlation is never omitted: `trace_id` is adopted/inherited/generated, `nt.storyId` falls back to the first root call (`Class.method`, else `unknown`), `nt.chapterId` to the story, `nt.traceName` to the resolved id — so a trace captured without any span still validates |
| Canonical schema **1.2** — one `SCHEMA_VERSION` for the entry form, the chapter envelope and the OTel attributes | Free | `nt.narrationTemplate` (1.1, the raw `@narrated` text with placeholders intact) plus the 1.2 identity fields: `nt.package`, `nt.exceptionPackage`, `nt.returnType`, parameter `type`, `thread.name`/`thread.id`/`nt.threadVirtual`. `nt.instanceId`, `code.filepath`/`code.lineno` and the process resource fields are declared but not captured (tracked in the private backlog) — all three are gated off by default in the Java runtime too |
| Per-test `.canonical.json` — the flat entry array, one enter + one exit per call | Free | `NARRATIVETRACE_CANONICAL=1`, independent of `format`. Context-free trees get sequential span ids and a **generated** trace id (eager identity, product ADR-014): span, story and chapter ids are derived and byte-stable across runs, while `trace_id`/`nt.traceName` are unique per capture and must be folded by the conformance normalizer before goldens are compared |
| Sequence diagrams — Mermaid + PlantUML | Free | `narrativetrace-diagrams` |
| Trace translation views — re-renders a captured trace into a locale the committed `glossary.json` covers; identifiers glossed with the original kept alongside, values/exception messages byte-identical, redaction untouched, a "glossary gaps" footer names every phrase left untranslated | Free | `narrativetrace-glossary`; live streaming via `TranslationSubscriber` (a pipeline observer beside the trace's own durable path, never a replacement) or one file per trace via `TranslationFileSink`; `./demo.sh --example <name> --lang es\|zh-CN` is the shipped example |
| Console test summaries with clarity scores | Free | |
| Flow summaries — aggregated paths + frequencies per entry point | Planned (Pro, gated) | Enterprise plan Phase E3 |
| Migration diffs — behavioral before/after comparison | Planned (Pro, gated) | Enterprise plan Phase E3 |
| Runtime dependency graphs (always-called vs conditional) | Planned (Pro, gated) | Enterprise plan Phase E4 |

## Keep your logging stack (logging + observability)

| Feature | Status | Notes |
|---|---|---|
| stdlib `logging` bridge — narrative events through your existing handlers under the `narrativetrace` logger, per-event-type level overrides | Free | Enter/return at DEBUG, exceptions at WARNING; [guides/logging.md](guides/logging.md) |
| MDC-style enrichment — `NarrativeContextFilter` stamps canonical correlation keys on every record; `request_log_scope` for request-level keys | Free | `traceId`/`spanId`/`nt.class`/`nt.method`/`nt.depth`/service identity |
| structlog processor emitting the identical key set | Free | `narrativetrace-structlog`; single vocabulary source (`current_scope_keys()`) |
| Coexistence with hand-written logs | Free | Remove them at your own pace |
| OpenTelemetry span export — live event listener + batch tree exporter, typed `narrative.*` attributes, orphan eviction | Free | `narrativetrace-otel`; [guides/opentelemetry.md](guides/opentelemetry.md) |
| Event pipeline — dual-path fan-out, bounded buffer, drain-threaded consumer with watchdog and load shedding | Free | Buffering/retention is free by design (product ADR-010) |
| Event-stream aggregation — aggregate tree, hotspots, error paths/rates, method/error frequencies (`EventAggregator`) | Pro | Relocated 2026-07-12 (Phase 31a) to the commercial distribution; feed it `EventStore.events()` |

## Improve the code (clarity diagnostics)

| Feature | Status | Notes |
|---|---|---|
| Clarity scoring — method / class / parameter naming quality from real traces (five weighted scorers, byte-identical dictionaries to Java) | Free | [guides/clarity.md](guides/clarity.md) |
| Suite-level clarity split + `clarity-results.json` / `clarity-report.md` via the pytest plugin | Free | |
| Standalone source scanner — `narrativetrace-clarity` console script, no tests required | Free | |
| Project vocabulary in scoring — the committed glossary extends the built-in dictionaries | Free | One file, one review workflow: verbs of the committed `glossary.json` score as domain verbs, its nouns as domain tokens. Read from `narrativetrace.glossary_dir` (default: working directory) once per session; reading is unconditional, unlike harvesting. Built-in tiers keep authority — generic verbs, boolean prefixes, meaningless placeholders, deprecated synonyms and `stale` terms are never promoted |
| Accepted abbreviations — a declared root-level `abbreviations` section of `glossary.json` | Free | Schema 2: `{"fx": "foreign exchange"}`. Only a listed token stops being asked to be spelled out — a token appearing inside a committed term does not, so `calc total` keeps the `calc` → `calculate` hint. Human-owned (harvest never writes it, merge carries it through); omitted when empty, so a glossary declaring none stays byte-identical at schema 1; readers accept it at any version |
| Vocabulary harvesting — pytest-suite hook (opt-in by `glossary.json` presence, `NARRATIVETRACE_GLOSSARY=off/on` overrides) merges new terms and flags deprecated-alias uses as `non-canonical-term` clarity issues, each with a mechanical rename suggestion | Free | Additive-only merge (human-authored fields never overwritten); a volatile `glossary-usage.json` reports what one run found, never committed |
| Static glossary scan — `glossary-scan` console script, no test run required; also the only place `@narrated`/`@on_error` narration templates are harvested (a captured trace already has values interpolated in) | Free | `narrativetrace-glossary`; a deliberate, opt-in write tool, not a CI gate |
| Optional CI gate — `--min-score`, `--max-high-issues` | Free | Advisory by default is recommended |

## Let AI agents see runtime truth (AI integration)

| Feature | Status | Notes |
|---|---|---|
| LLM-oriented docs (`llms.txt`, `llms-full.md`) | Free | |
| MCP analysis tool handlers | Planned (Pro, gated) | Enterprise plan Phase E5 |

Note: value separation happens at capture time (product ADR-002 — below
DETAIL, parameter values are never recorded), but the second per-test
AI-safe *structural* trace file some runtimes write has no Python
counterpart yet;
the pytest plugin writes one full-detail file per test.

## Pro tier (commercial)

The Python Pro tier ships as a separate commercial distribution
(proprietary license, never published to PyPI). Event-stream aggregation was relocated there from this repo's
free core on 2026-07-12 (Phase 31a Stage 2): **`EventAggregator` — Pro**.
Flow summaries, migration diffs, dependency-graph diagrams, and MCP tool
handlers are **Planned (Pro, gated)** — execution waits on a paying
Python-stack engagement per that repo's private implementation plan
(Phases E3–E5). Audit & compliance is **not planned** for Python (Phase E6).

---

## Keeping this guide honest

Adapted from the canonical guide's rules:

1. Every user-visible feature of NarrativeTrace for Python appears here,
   exactly once, with a status.
2. A feature moves to **Free**/**Pro** only when it is merged, tested,
   and documented. "In development" means the design is settled and work
   is scheduled; "Planned" means specified only.
3. Changes that add or promote a feature must update this file in the
   same commit.
4. This guide covers only what NarrativeTrace for Python ships. Product-wide
   features and their cross-platform statuses live in the canonical
   guide (linked at the top) — do not fork its rows here; record only
   the Python-side reality (including honest gaps).
