# Structural Trace Format (`.nt`)

*(since 0.1.2, unreleased)*. The AI-safe structural trace artifact (product ADR-002): one
file per test scenario containing only the developer-authored *shape* of the behavior —
zero runtime values. This format is **cross-platform**: every NarrativeTrace runtime emits
the identical format, which is what lets approved traces and conformance fixtures travel
between platforms. This page mirrors the reference runtime's own structural-format spec —
the grammar below is normative and identical in every language this product ships in.

## Files and naming

| File | Role |
|---|---|
| `<output_dir>/structural/<TestClass>/<slug>.nt` | Emitted alongside the Markdown trace; the file on disk is the **last-green baseline** — a non-green run compares against it (console delta, failure report) but never overwrites it. "Green" is the whole verdict: a test that passed but whose structure approval mode *rejected* ends non-green, so a rejected structure never becomes the baseline and reverting the change reports no delta |
| `<approved_dir>/<TestClass>/<slug>.approved.nt` | Committed approved trace (opt-in via `NARRATIVETRACE_APPROVAL=true`, directory configurable via `NARRATIVETRACE_APPROVED_DIR`, default `test-narratives`) — a passing test whose structure differs fails with a readable diff |
| `<slug>.received.nt` | Written beside the approved trace on a mismatch (or when no approved trace exists yet); review it, then promote via `uv run poe approve` or the `narrativetrace-approve` console script |
| `<slug>.incomplete.nt` | The same content, written instead of `.received.nt` when the run itself was incomplete (the best-effort path dropped events, or refused an async scope at the adoption cap). The approve verb ignores it by name: a short run must never become the committed baseline, or every later complete run reads as having *added* calls. Such a run is compared by subsequence containment rather than equality — absences are tolerated and named, anything added or reordered still fails |

The format extension is last (`.approved.nt`, ApprovalTests convention) so editors and diff
viewers key off `.nt`. Note: `.nt` collides with RDF N-Triples in some syntax-highlighting
maps; register an override in `.gitattributes` where it matters.

### Artifact identity (cross-platform)

`<slug>` above is the **artifact identity** of one test invocation, and every runtime
spells it the same way — an artifact written by one runtime is found under the same name
by another:

- An ordinary test method is its slugged name: camel-case split on `_`, lowercased,
  everything outside `[a-z0-9_]` replaced with `_` — `customerPlacesOrder` →
  `customer_places_order`.
- One invocation of a test that runs more than once (any `@pytest.mark.parametrize`
  case, or a parametrized fixture) appends `-<index>-<label>`: the 1-based invocation
  number zero-padded to three digits, then the invocation's readable label through the
  same slug rule with runs of `_` collapsed and the ends trimmed — `equipment_can_be_found
  -002-find_tent`. A label that slugs to nothing is dropped, leaving
  `equipment_can_be_found-002`.
- `-` is the separator precisely because the slug alphabet cannot produce one. The
  index — not the label — is what makes the scheme collision-proof: two invocations
  always differ in it, so labels that differ only in characters a path cannot carry still
  get separate files. The label is what makes the name readable.
- The name is stable across runs, machines and processes, which is what lets one
  invocation's `.approved.nt` be committed at all. Where a name exceeds the 255-byte
  path-element limit the *method* half is truncated and given eight hex characters of the
  Java `String.hashCode` of the full slug — specified, therefore identical everywhere; a
  per-process hash would silently invalidate every baseline it touched.

Because artifact names are derived rather than announced, a run also writes
`<output_dir>/manifest.json`: one row per traced scenario naming its test, its invocation
number and every file it owns. Read that when you know the scenario and want the file.

> An invocation's `scenario:` header is **not** its display name. A `parametrize` id
> interpolates arguments into the test's display name, so this artifact — the value-free
> one — is titled by the method and the invocation number instead: `Equipment can be
> found #2`. A test that runs once keeps the display name it always had, so no committed
> approved trace moves. The *filename* still carries the slugged label, because that is
> what tells two invocations apart on disk, and `manifest.json` — an index over the
> value-carrying artifacts too — names the scenario as pytest displayed it. Keep secrets
> out of parametrize ids.

## Content

```
scenario: Weekend trip settles with three transfers

- TripSettlementService.record_expense(trip_name, expense)
  - ExpenseValidator.ensure_valid(expense)
  - TripLedger.record_expense(trip_name, expense)
- TripSettlementService.settle_trip(trip_name) → value
  - TripLedger.expenses_of(trip_name) → value
  ~ fork [2]
    - BalanceCalculator.compute_balances(expenses) → value
    - StockService.check() → value
```

- **Header:** `scenario: <humanized test name>` + blank line. Nothing else — no result,
  no trace ids/names, no dates. One invocation of a test that runs more than once is
  `scenario: <humanized method name> #<index>` — a parametrize id's arguments never reach
  it.
- **Call line:** `ClassName.method_name(param_name, param_name)` — names only, capture
  order, two-space indent per depth.
- **Outcome kinds:** non-`None` return ` → value`; a `None`/void-shaped return: nothing;
  thrown ` !! ExceptionSimpleName` (type is structure; the message is a value and never
  appears); unmatched enter ` ?? incomplete`.
- **Concurrency:** fork groups render `~ fork [n]` and work adopted from a propagated
  context snapshot (a thread or `asyncio` task picking up work under an activated
  snapshot) renders `~ async [n]`, both with members **sorted by `Class.method`** —
  capture order across threads/tasks is the scheduler's choice, not behaviour, so the
  artifact states the set and nesting of concurrent work and never its order. Async
  groups are keyed by the launching span, so every async child of one call is one group,
  and they appear at root level too when the work outlived its caller. Fire-and-forget
  renders `~ fire-and-forget` + children. Thread names/ids never appear.
- **Excluded by design:** all argument/return values, exception messages, durations,
  timestamps, thread identity, trace/span ids, trace names, run results, and narration
  (resolved narration embeds values).
- **Encoding:** UTF-8, LF, trailing newline. Identifiers pass through
  control-character sanitization.

## Guarantees

1. **Deterministic:** identical behavior ⇒ byte-identical file. This is what makes the
   artifact the approved-trace baseline and the conformance-fixture golden format.
2. **Value-free:** zero prompt-injection surface, zero PII, minimal tokens — safe to
   hand to an AI agent by default.
3. **Division of labor:** the artifact asserts behavioral *shape*; value correctness
   remains the job of test assertions. A change that only alters a return value with
   identical structure does not change the artifact — by design.

## Known gap

This runtime does not yet emit the value-free JSON sibling some other runtimes ship
(`<test>.structural.json`, a `.canonical.json`-shaped array with every value elided) — the
`.nt` text format above is this runtime's only structural artifact today. Tracked as
follow-up work; `.canonical.json` (the value-carrying JSON entry array) is unaffected and
continues to carry full detail.

Implemented in this repository by `narrativetrace.render.structural.StructuralTraceRenderer`,
emitted by the `narrativetrace-pytest` plugin beside the `.md`/`.json`/`.mmd` companions —
see the [pytest Guide](guides/pytest.md), [Configuration Guide](guides/configuration.md)
and [What to Commit](what-to-commit.md).
