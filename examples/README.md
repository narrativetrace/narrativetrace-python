# NarrativeTrace Examples

Runnable tutorials that show NarrativeTrace in practice. This directory is **not published** —
it exists so a developer (or an AI agent) can run a realistic scenario, read the resulting
trace, and connect it back to the code that produced it.

Treat the modules as tutorials with a suggested order, not as a reusable API. Each example's
module docstring carries a guided reading order; start there when drilling into one.

## Subproject map

| Example | Entry point | What it teaches |
|---|---|---|
| `ecommerce` | `python -m examples.ecommerce` | The flagship: a shop's order flow through `trace_object`-wrapped services — `@narrated`, `@on_error`, `@not_traced`, two concurrency flavors in one trace (thread-pool fork-join for the pricing quotes, a `ForkJoinGroup` created from inside a genuine `async def` for the notification fan-out), fire-and-forget, success and failure scenarios, and a worker thread capturing its own trace. |
| `hotel_booking` | `python -m examples.hotel_booking` | How the clarity subsystem scores naming quality, using a hotel-reservation domain with deliberately excellent, adequate, and poor names, plus a cohesion mismatch — and the clarity report over all four. |
| `minecraft` | `python -m examples.minecraft` | How much naming alone changes trace quality: the same behavior traced twice with five collaborators each, once with domain-rich names, once with generic ones, scored side by side. |
| `library` | `python -m examples.library` | The value side of tracing: frozen dataclasses that narrate themselves through `@narrative_summary` in a small book-lending domain, with a successful borrow and an unavailable-book failure. |
| `fastapi_service` | `uvicorn examples.fastapi_service.fastapi_service:app` | A Starlette/FastAPI app traced end-to-end by the ASGI middleware: a fresh context per request, exported with the real status code at the request boundary. Not part of the demo launcher — it needs a server. |
| `tour.py` | *(shared scaffolding, no entry point)* | `Scenario` (title, wiring note, `run(context)`), the console sections (`--- Trace tree ---`, `--- Prose ---`, `--- Markdown ---`, `--- Mermaid ---`, `--- PlantUML ---`), and `narrated_run`, the live `→ ← !!` stream with its demo and classic formatters. |

## Running the examples

Every console example walks its scenarios and prints, per scenario, the live narration as the
code runs followed by the renderings of the captured tree:

```bash
uv run python -m examples.ecommerce
uv run python -m examples.hotel_booking
uv run python -m examples.minecraft
uv run python -m examples.library

uv run python -m examples.ecommerce --classic   # the same run as ordinary timestamped log lines
```

Each example exposes `scenarios() -> list[Scenario]` and `run_example(out, *, classic=False)`;
the tests under each directory assert that every scenario carries a wiring note and runs.

## Where the logger is configured

"Send it to your logger" ([documentation/guides/logging.md](../documentation/guides/logging.md))
is not a snippet you have to add yourself — every example already ships it, in the idiomatic
place a real project would put it, alongside the console narration:

| Example(s) | Where | What |
|---|---|---|
| `ecommerce`, `hotel_booking`, `library`, `minecraft` | [`examples/tour.py`](tour.py) — `narrated_run` / `_configure_realistic_logger` | `logging.basicConfig` plus `NarrativeContextFilter`, shared by every console example so there is one pattern, not four; `LoggingTraceConsumer` on the `narrativetrace` logger reaches it by propagation |
| `fastapi_service` | [`examples/fastapi_service/fastapi_service.py`](fastapi_service/fastapi_service.py) — `build_app` / `_configure_realistic_logger` | the same `logging.basicConfig` + `NarrativeContextFilter` recipe, wired at the ASGI composition root; `NarrativeContextFilter` also stamps `httpMethod`/`httpRoute`/`clientIp` from the middleware's `request_log_scope` |
| `./demo.sh` (any example) | [`examples/demo/launcher.py`](demo/launcher.py) — `_route_realistic_logger_to_a_file` | claims `logging.basicConfig` first and points it at `narrative-traces/demo.log` instead of the terminal, so the raw DEBUG lines don't drown the colorized, paced walk; run the example directly (`python -m examples.<name>`) to see the same line on your terminal instead |

Run any console example with `2>&1 1>/dev/null` (or just watch stderr) to see it: the enter/return
lines you already saw on stdout as `→`/`←` narration also print through the stdlib `logging`
module, timestamped, at `DEBUG`, from the `narrativetrace` logger — exactly what
`logging.basicConfig` in a real entry point, plus the bridge the repo ships, gets you.

## Demo launcher

`./demo.sh` (repository root) is the fastest way to watch the examples from a fresh clone — it
installs the workspace on first run, then hands off to `uv run poe demo` (equivalently
`python -m examples.demo`, once the workspace is already synced): one command, the live narration
colorized and indented by call depth, and every rendering announced as its own section. Without
arguments it opens an interactive picker; `--example <name>` runs non-interactively; `--list`
enumerates the examples.

**It walks, it does not scroll.** On a terminal the demo stops after every scenario —
`[Enter]` moves on, `q` quits — and each scenario opens with a note on *how that scenario's
trace is configured*: which `trace_object` wrappers, which of `@narrated` / `@on_error` /
`@not_traced` produced what you are about to read, how the thread-pool work joins the trace.
The notes live on the scenarios themselves (`Scenario.wiring`), so a scenario cannot lose its
note: `Scenario` rejects a blank one, and each example's tests walk every scenario. Paced runs
are recorded first and then walked, so a stop point can never inflate the durations the trace
tree reports; `--no-pause` plays the run straight through and is what pipes and CI get.

**Where the renderings come from** is answered once per run, at the first rendering section.
There is no default renderer and nothing to configure: capture produces a `TraceTree` and you
call the renderer you want (`IndentedTextRenderer().render(tree)`); a renderer is any callable
from `TraceTree` to `str`. The live `→ ← !!` lines are not a renderer at all — that is
`LoggingTraceConsumer` fed from the context's event store, the only view that costs no
rendering code. Configuration selects a renderer in exactly one place, trace files written from
tests: `NARRATIVETRACE_OUTPUT=true` plus `NARRATIVETRACE_FORMAT=markdown|text|mermaid|plantuml`
(`markdown` is the default; `narrativetrace.toml` and `pyproject.toml` set the same keys).

**Classic log output is a first-class mode.** The narration is ordinary `logging`, so it renders
in the traditional format every log tool ingests — timestamp, level, thread, and logger name,
with `NarrativeContextFilter` stamping the span keys onto each record:

- `uv run poe demo --example <name> --classic` — the whole run through the classic format,
  verbatim, no styling.
- `python -m examples.<name> --classic` — the same, without the launcher.

**Terminal policy.** Colors follow `NO_COLOR` (strips colors, keeps the structure),
`FORCE_COLOR` (styled output even into a pipe — for recordings), and whether stdout is a
terminal; a plain pipe gets the example's verbatim output. Stop points need a terminal on both
ends and never apply to `--classic`.

**Translated traces.** `--lang es|zh-CN` re-renders the same recorded run through the chosen
example's committed `glossary.json`: identifiers are glossed with the original kept alongside
them, values and exception messages stay byte-identical, and any untranslated phrase lands in a
"glossary gaps" footer at the end of its scenario — `TraceTranslationView` under the hood
(`narrativetrace-glossary`). All four demo-picker examples have a committed glossary; `ecommerce`
and `library` cover every `@narrated`/`@on_error` narration template, `ecommerce` alone covers
both `es` and `zh-CN`. `--classic` has no translated variant (it is raw, unstyled logging output)
and is refused together with a non-English `--lang`. On a terminal, picking an example through the
interactive picker (no `--example`) is followed by a language menu whenever that example's
glossary covers more than one locale; an explicit `--lang` always wins and skips it. Try it:

```bash
uv run python -m examples.demo --example ecommerce --no-pause --lang es
uv run python -m examples.demo --example ecommerce --no-pause --lang zh-CN
```

## The examples in detail

### ecommerce — the shop

`OrderService.place_order` resolves the customer, prices the line, reserves stock, quotes
discount and shipping concurrently on a thread pool (a `ForkJoinGroup` whose children merge
back under the order span), charges the card, and launches the order-confirmed notification
through a `FireAndForgetGroup` on the same pool. That launched notification is where a second,
genuinely different concurrency mechanism lives: `AsyncNotificationService.notify_order_confirmed`
is a real `async def`, traced like any other method — its own `ForkJoinGroup`, created *from
inside* the running coroutine, fans email confirmation and loyalty-points credit out over
`asyncio.gather` and merges them back under it. One trace shows both: thread-pool fork-join for
the pricing quotes, an asyncio fork-join for the notification fan-out — the latter nesting
correctly under its coroutine, rather than dropping as roots, only because of a 2026-09-08 core
fix (`current_span_id` now resolves the async scoped parent). Six scenarios:

1. **Successful order + async notification** — rendered as tree, prose, Markdown, and Mermaid.
2. **Payment failure — inventory leak bug** — the trace exposes that `InventoryService.reserve`
   was called but `release` never was.
3. **Flaky external service** — a decorator (`FlakyNotificationService`) wrapped at runtime
   succeeds once, then fails.
4. **Unknown customer** — input-validation failure branch.
5. **Out of stock** — business-rule failure branch, before the parallel quotes.
6. **Explicit async capture** — a worker thread captures its own two lookups and hands the
   tree back; the main-thread lookup is not in it.

Key supporting pieces: `build_shop` (the composition root: every service wrapped once with
`trace_object`), `Collaborators` (one port per service plus the pool), `AsyncNotificationService`
plus its `EmailService`/`LoyaltyService` collaborators (the asyncio fan-out), and the in-memory
adapters for customers, catalog, inventory, discount, shipping, and payment so the trace stays
easy to follow.

### hotel_booking — what the clarity analyzer rewards and penalizes

Four scenarios over a hotel-reservation domain, each at a different naming-quality tier:
`ReservationService` (excellent), `BookingManager` (adequate), `DataProcessor` (poor), and
`GuestRepository` (a cohesion mismatch). After running all four it feeds the captured traces to
`narrativetrace_clarity.analyze` and prints the per-scenario reports plus the suite summary, so
you can connect each score back to the naming choices that caused it.

### minecraft — naming quality, contrasted directly

`refactored.py` and `unrefactored.py` perform the same "player joins world" work with five
collaborators each (`WorldServer`, `WorldGenerator`, `PlayerInventory`, `CraftingTable`,
`CreatureSpawner` versus `GameManager`, `DataProcessor`, `StateManager`, `ThingFactory`,
`EntityHandler`). Both run back to back, wired byte for byte the same, and the clarity scores at
the end put a number on the difference.

### library — values that tell their own story

A book-lending domain (`CatalogService`, `MemberService`, `LendingService`) whose frozen
dataclasses carry a `@narrative_summary` method, so `Book` reads as "The Pragmatic Programmer by
David Thomas & Andrew Hunt" in the trace rather than as a field dump. A successful borrow and a
`BookUnavailableError` failure, rendered as tree, prose, Mermaid, and PlantUML. A
Jupyter-notebook variant is tracked in the private backlog.

### fastapi_service — the ASGI slice

A Starlette app wrapped by `NarrativeTraceMiddleware`: each request runs in a fresh narrative
context, the handler resolves it with `get_narrative_context()`, and the exporter receives the
captured tree with the real status code and duration at the request boundary.

## Quality gates

The examples are excluded from publishing and from the coverage denominator, but they are
**not** exempt from code quality: `ruff` (format and lint), `mypy --strict`, and the pytest
suite all apply — `uv run poe check` runs them. `examples/**/test_*.py` are collected with the
rest of the workspace.
