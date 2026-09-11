# NarrativeTrace™ (Python)

**English** | [Español](LEAME.md) | [Português](LEIAME.md) | [简体中文](自述文件.md)

> Code is the log.

NarrativeTrace turns running Python code into a readable execution narrative, built from the
method, class and parameter names you already wrote. No `logger.info(...)` lines. If the trace is
unreadable, your code needs better names — not more log statements.

In a hurry: [try it locally](#try-it-locally) → [add it to one test](#add-it-to-one-test) →
[pick your integration](#choose-your-integration).

## The problem

Half of this method is logging noise:

```python
def place_order(self, customer_id, product_id, quantity):
    logger.info("Placing order for customer %s product %s qty %s", customer_id, product_id, quantity)
    inventory = self.inventory.reserve(product_id, quantity)
    logger.debug("Reserved inventory: %s", inventory)
    payment = self.payments.charge(customer_id, inventory.total)
    logger.info("Payment processed: %s", payment.transaction_id)
    return OrderResult(payment.transaction_id, inventory.items)
```

The business logic is three lines; the logging is four. Every developer writes those logs
differently — different messages, different levels, different values included. The result is
inconsistent, verbose, and tangled with the code it describes.

NarrativeTrace eliminates this entirely:

```python
def place_order(self, customer_id, product_id, quantity):
    inventory = self.inventory.reserve(product_id, quantity)
    payment = self.payments.charge(customer_id, inventory.total)
    return OrderResult(payment.transaction_id, inventory.items)
```

Pure business logic. The trace is generated from the method names, parameter names, and return
values — the information that was already there.

## What the output looks like

Wrap the collaborators once and run the code; here is the real output of a three-service order
flow (`OrderService` calling an `InventoryService` and a `PaymentService`, both also wrapped):

```
OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3)
├── InventoryService.reserve(product_id: "prod-42", quantity: 3) → "reserved 3 of prod-42" — 0ms
├── PaymentService.charge(customer_id: "cust-1", amount: 30) → "txn-cust-1-30" — 0ms
└── → "order placed: txn-cust-1-30" — 0ms
```

**When something goes wrong**, the trace makes the bug visible:

```
OrderService.place_order(customer_id: "cust-broke", product_id: "prod-7", quantity: 3)
├── InventoryService.reserve(product_id: "prod-7", quantity: 3) → "reserved 3 of prod-7" — 0ms
├── PaymentService.charge(customer_id: "cust-broke", amount: 30) !! PaymentDeclinedError: payment declined for customer cust-broke — 0ms
└── !! PaymentDeclinedError: payment declined for customer cust-broke — 1ms
```

`InventoryService.reserve` was called but `InventoryService.release` is nowhere in the trace — the
bug is visible without a debugger.

**The trace is only as good as your names.** The same "player joins world" flow from
[`examples/minecraft`](examples/minecraft), traced twice — once with domain names, once with
generic ones, both runs real:

```
→ WorldServer.player_joined(player_name: "Steve")
  → WorldGenerator.generate_chunk(x: 0, z: 0)
  ← WorldGenerator.generate_chunk → Chunk(x=0, z=0, biome="plains")
  → PlayerInventory.add_item(item: Item.OAK_LOG, quantity: 4)
  ← PlayerInventory.add_item → True
  → CraftingTable.craft(recipe: Recipe.WOODEN_PICKAXE)
  ← CraftingTable.craft → Item.WOODEN_PICKAXE
  → CreatureSpawner.spawn_hostile(type: CreatureType.ZOMBIE, x: 10, y: 64, z: 20)
  ← CreatureSpawner.spawn_hostile → Creature(type=CreatureType.ZOMBIE, x=10, y=64, z=20)
← WorldServer.player_joined → "Steve joined the world"
```

```
→ GameManager.handle(input: "Steve")
  → DataProcessor.process(a: 0, b: 0)
  ← DataProcessor.process → DataResult(a=0, b=0, tag="plains")
  → StateManager.update(type: 1, count: 4)
  ← StateManager.update → True
  → ThingFactory.create(type: 1)
  ← ThingFactory.create → 1
  → EntityHandler.execute(kind: 1, a: 10, b: 64, c: 20)
  ← EntityHandler.execute → Entity(kind=1, a=10, b=64, c=20)
← GameManager.handle → "Steve joined the world"
```

Same call graph, same return values, only names differ — `narrativetrace-clarity` puts a number on
the difference (0.72 vs. 0.53 for the two runs above). If your code can't tell its own story, it
needs refactoring, which is why NarrativeTrace also
[scores your naming](documentation/guides/clarity.md).

### Why this matters for AI-assisted development

Every `logger.info(...)` line is a line that AI coding tools have to parse, spend tokens on, and
reason around. Remove them and the same token budget covers more of your actual code, the model
sees what the code does rather than how it logs, and pull requests show business-logic changes
instead of mixed logic-and-logging changes.

### How it compares

Unlike an OpenTelemetry span tree (built for machines and dashboards), a NarrativeTrace reads as
prose for humans and LLMs. The two compose: `narrativetrace-otel` emits the same trace as typed
OTel spans, so you get the human narrative *and* the backend correlation from one capture.

### It doesn't replace your logging stack

NarrativeTrace is not a logging framework. It ships no handler, no formatter, no shipping
pipeline — your `logging` configuration (handlers, formatters, `dictConfig`/`fileConfig`) or your
structlog processor chain keeps running exactly as it is today.

What it replaces is the hand-written narration *statements* — the `logger.info("Placing order
%s for customer %s", ...)` lines from [the problem](#the-problem) above. A traced method produces
that same narrative automatically, from the real parameter and return values at the call, with
zero narration code in the method body. That narrative is captured through its own path — not by
intercepting or reconfiguring your logging pipeline.

Two optional bridges let that narrative — or just its identity — ride your existing stack,
unmodified:

- **`LoggingTraceConsumer`** feeds the generated enter/return/exception lines through
  `logging.getLogger("narrativetrace").log(...)` — the same call a hand-written statement would
  make, so every handler and formatter you already have keeps receiving them, untouched.
- **`narrativetrace-structlog`** doesn't generate lines at all: its processor stamps the same
  correlation keys (`traceId`, `spanId`, `nt.class`, `nt.method`, …) onto every event dict already
  flowing through your processor chain, including the ones you wrote by hand.
  `NarrativeContextFilter` does the stdlib-`logging` equivalent, as a `Filter` on your own handler.

A hand-written `logger.info(...)` next to a traced call intermixes freely — same logger, same
stream, same handlers. NarrativeTrace only adds to what is already there.

## Try it locally

No project, no wiring — from a clone of this repository, run the flagship example live:

```bash
./demo.sh --list                                   # ecommerce, hotel_booking, minecraft, library
./demo.sh --example ecommerce --no-pause           # the flagship: fork-join, redaction, failures
./demo.sh --example ecommerce --classic            # the same run as ordinary timestamped logs
./demo.sh --example ecommerce --lang es            # the same trace, narrated in Spanish (zh-CN too)
```

`./demo.sh` installs the workspace on its first run (`uv sync --all-packages`, frozen lockfile)
and is silent on every run after — no separate setup step.

Without `--no-pause` the demo stops after each scenario — `[Enter]` continues, `q` quits — and
each scenario opens with a note on how *that* trace is wired. A slice of the real output:

```
→ OrderService.place_order(customer_id: "C-1234", product_id: "SKU-MECHANICAL-KB", quantity: 2)
  → CustomerService.find_customer(customer_id: "C-1234")
  ← CustomerService.find_customer → Customer(id="C-1234", name="Alice Johnson", tier=CustomerTier.GOLD)
⑂ fork group created [groupId: fork-1]
→ DiscountService.calculate_discount(customer_id: "C-1234", product_id: "SKU-MECHANICAL-KB")
← DiscountService.calculate_discount → Discount(percent=10)
⑃ fork joined [groupId: fork-1, members: 2]
  → PaymentService.charge(customer_id: "C-1234", amount: 166.97, card_token: [REDACTED])
  ← PaymentService.charge → PaymentConfirmation(transaction_id="TXN-00001", amount=166.97)
```

Outside this repository, the same shape needs no project at all — install and run:

```bash
uv add narrativetrace
```

`narrativetrace` — the package this snippet needs — is live on PyPI; the optional integration
packages are rolling out one at a time (see the [Packages](#packages) table below). Until the one
you need is on the index, work from a checkout of this repository (`uv sync --all-packages`).

```python
from narrativetrace import ContextVarNarrativeContext, MarkdownRenderer, trace_object


class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


context = ContextVarNarrativeContext()
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

print(MarkdownRenderer().render(context.capture_trace()))
```

See [examples/README.md](examples/README.md) for what each of the four demo examples teaches, and
the [`fastapi_service`](examples/fastapi_service) example for the ASGI slice (not in the demo
launcher — it needs a running server).

## Add it to one test

The shortest path from "interesting library" to "I saw a useful trace of my own code" is the
pytest plugin. Python ≥ 3.12.

**1. Install it** — pulls in the core, the diagram renderers, and the clarity engine:

```bash
uv add --dev narrativetrace-pytest
```

**2. Trace one service in one test** — the plugin registers itself; just request the fixture:

```python
from narrativetrace import trace_object

class TestOrderService:
    def test_customer_places_order(self, narrative_trace):
        service = trace_object(OrderService(), narrative_trace)
        service.place_order("C-1234", "SKU-KB", 2)
```

**3. Turn on artifact output and run the suite:**

```bash
NARRATIVETRACE_OUTPUT=1 uv run pytest
```

**4. Open the narrative** — the test class became the directory, the test method became the file:

```text
narrative-traces/traces/TestOrderService/test_customer_places_order.md
```

This is real, run-for-real output from that exact test:

```markdown
---
type: trace
scenario: Test customer places order
entry_point: OrderService.place_order
duration_ms: 0
trace_id: aa4ae2eaa56e7e49b7aa42aece5999f0
trace_name: muted stone tests
method_count: 1
error_count: 0
---

## Trace: OrderService.place_order

**Scenario:** Test customer places order
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **OrderService.place_order**(customer_id: `"C-1234"`, product_id: `"SKU-KB"`, quantity: `2`) → `"ORD-C-1234-SKU-KB-2"` — 0ms
```

Every test writes its own artifact set — companion `.json` and `diagrams/<Class>/<slug>.mmd` for
the default `markdown` format, plus a suite-wide `clarity-report.md`:

```text
narrative-traces/
├── traces/<TestClass>/<slug>.md         the human narrative
├── traces/<TestClass>/<slug>.json       the same trace as canonical JSON
├── diagrams/<TestClass>/<slug>.mmd      Mermaid sequence diagram
├── clarity-results.json                 naming scores, one entry per test
└── clarity-report.md                    naming feedback for the whole suite
```

Want to keep going — rename the method and watch the clarity score drop, add `@not_traced` and
see a value redacted? → [First 10 Minutes](documentation/first-10-minutes.md) walks both with real
output.

## Choose your integration

Tests are where most people start. This is where you go next:

| You want | Start with |
|---|---|
| Traces in tests, least wiring | `narrativetrace-pytest` (`narrative_trace` fixture) |
| Explicit control over what gets wrapped, in plain Python | `trace_object(obj, context)` — the core, no framework required |
| FastAPI/Starlette request lifecycle | `narrativetrace-asgi` |
| Propagate a trace to a downstream HTTP call | `narrativetrace-asgi`'s `attach_traceparent` (httpx) |
| Traces in your production log stream | `LoggingTraceConsumer` / `NarrativeContextFilter` (core) |
| structlog pipelines | `narrativetrace-structlog` |
| OpenTelemetry spans | `narrativetrace-otel` |
| Sequence diagrams | `narrativetrace-diagrams` |
| Naming-quality CI gate | `narrativetrace-clarity` console script |
| Flask (WSGI) or Django | Not shipped yet — see [Choosing an Integration](documentation/choosing-an-integration.md) |

There is no zero-code, bytecode-level attachment mechanism here — every path above is an explicit
`trace_object(...)` call or middleware you register yourself; nothing rewrites your classes as
they load. Full detail, a decision diagram, and what happens when NarrativeTrace stacks with other
wrappers: [Choosing an Integration](documentation/choosing-an-integration.md).

### Packages

| Package | Purpose |
|---|---|
| [`narrativetrace`](packages/narrativetrace) | Dependency-free core: capture, decorators, rendering, redaction, concurrency, JSON export, logging bridge |
| [`narrativetrace-pytest`](packages/narrativetrace-pytest) | pytest plugin: per-test `narrative_trace` fixture, artifacts, clarity footer |
| [`narrativetrace-diagrams`](packages/narrativetrace-diagrams) | Mermaid + PlantUML sequence-diagram renderers |
| [`narrativetrace-otel`](packages/narrativetrace-otel) | OpenTelemetry span bridge (live listener + batch exporter) |
| [`narrativetrace-asgi`](packages/narrativetrace-asgi) | ASGI middleware (Starlette/FastAPI), W3C traceparent, request accessor |
| [`narrativetrace-clarity`](packages/narrativetrace-clarity) | Naming-clarity engine + CI gate console script |
| [`narrativetrace-structlog`](packages/narrativetrace-structlog) | structlog processor injecting correlation keys |
| [`narrativetrace-glossary`](packages/narrativetrace-glossary) | Domain glossary: the `glossary.json` model, deterministic reader/writer, Markdown view |

## Privacy and safety

This library runs inside your process and writes files your team will share. What that means, on
one screen:

| Surface | Can disable built-in redaction? |
|---|---|
| pytest plugin, ASGI middleware, OTel bridge, structlog processor, stdlib logging bridge | No |
| A custom `ValueRenderer` your own code constructs | Yes — only by passing `RedactionPolicy.DISABLED` explicitly |
| `@not_traced` / `not_traced_field(...)` | Not applicable — it is what does the redacting, and it always wins |

`@not_traced` on a parameter or field, and the name-based deny-list (`password`, `token`, `cvv`,
`ssn`, …) plus value-shape masking (JWT/PAN/`Set-Cookie`-shaped strings, regardless of field name),
apply everywhere a value is reflectively rendered — no shipped integration exposes a way around
them. One known, documented narrowness: a `{param.path}` narration template always checks the
default deny-list, even when the surrounding renderer was built with a custom or disabled policy —
see [Privacy and Redaction](documentation/privacy-and-redaction.md) for the exact scope.

- **Tracing failures cannot fail your application.** Recording is exception-isolated on every
  path; a raising `__str__` or a full buffer never changes what your method returns or throws.
- **Resource use is bounded.** The buffered analysis path is a fixed-size ring (65,536 events by
  default) that sheds rather than blocks under load — and says so: a run that lost events prints
  the count in its own suite footer instead of silently under-reporting.
- **Introspection reads stored data, not code.** A computed `@property` getter never runs; the
  only members NarrativeTrace invokes are a custom `__str__`, a `@narrative_summary` method, and
  property paths named in a `@narrated`/`@on_error` template — keep those pure, as you would for a
  debugger.

→ [Privacy and Redaction](documentation/privacy-and-redaction.md) for the row-by-row contract
verified against the code.

**Coexisting with other wrappers.** Contract libraries, DI/AOP proxies, and observability agents
(OpenTelemetry auto-instrumentation among them) can wrap the same method NarrativeTrace does. This
runtime holds two rules for its own mechanisms: one trace frame per business-boundary crossing —
bridge methods and container-generated machinery are never narrated — and no outcome depends on
which wrapper sits outer, so a wrapped call's result or exception always reaches the trace
regardless of stacking order. `narrativetrace-asgi`'s `excluded_paths` is the one exclusion knob
shipped today (path-scoped, exact match); `trace_object` has nothing to exclude by pattern, since
it wraps one instance you hand it, not a sweep.

## Performance

Capture is gated by a tracing level checked *before* any rendering happens
(`NARRATIVETRACE_LEVEL`): set it to `OFF` and the wrappers short-circuit — no reflection, no
string work — before touching your arguments. For hot loops, narrow the traced scope or drop the
level rather than tracing everything.

A starter benchmark suite exists (`packages/narrativetrace/tests/test_bench_*.py`, run with
`uv run poe bench`): capture overhead per tracing level, a call through `trace_object` against a
direct call, rendering a captured trace to each format, and the redaction check on a hot path.
We have not yet published official numbers from it the way the Java sibling publishes JMH
figures — `uv run poe bench-gate` compares a run against the previous one on the *same* machine
(host-baseline numbers are not comparable across machines), which is why this is a nightly
habit, not a public number. Do not assume the Java numbers transfer: the runtimes, and what each
line of tracing code costs on them, are different. We will not claim "zero overhead" either
way — tracing does work, and work costs something.

## What is free and what is Pro

**Free** is everything in this repository — source-available under BSL 1.1, free in production,
converting to Apache 2.0 four years after each release: the whole runtime, per-test traces in
every format, clarity scoring, the domain glossary, and every integration in the table above.

**Pro** is intelligence *across* runs, built on the same capture: today that is event-stream
aggregation (`EventAggregator` — aggregate trees, hotspots, error rates), shipped in a separate
commercial distribution, never in this one. Flow summaries, migration diffs,
runtime dependency graphs, and MCP tool handlers for AI agents are planned there next. The
[Feature Guide](documentation/feature-guide.md) is the authoritative status table: it labels every
feature Free, Pro, In development, or Planned, and cites the code behind each shipped row.

## Concurrency

Fork-join and fire-and-forget groups propagate the full trace identity across `asyncio` tasks and
thread pools, so concurrent work is grafted back under the launching span with a shared group id —
the story stays coherent even when the execution isn't sequential. A context snapshot carries the
trace *into* a worker and the work traced there comes *back*: the capturing stack reports it from
the moment it is published, transitively through a chain of async hops.

## Development

```bash
uv sync --all-packages
uv run poe check          # format-check + lint + typecheck + lint-imports + coverage + stress-quick + metrics + clarity + no-license-headers + translation-check + legal-check + bandit
```

## Documentation

Start here:

- [First 10 Minutes](documentation/first-10-minutes.md) — one tiny service, real output, from install to a redacted value
- [Choosing an Integration](documentation/choosing-an-integration.md) — which package you need, as a decision diagram
- [Installation Guide](documentation/guides/installation.md) — every package, what it adds
- [Configuration Guide](documentation/guides/configuration.md) — tracing levels, output settings, precedence chain
- [Decorators Guide](documentation/guides/decorators.md) — `@narrated`, `@on_error`, `@not_traced`, the purity contract

Going deeper:

- [Privacy and Redaction](documentation/privacy-and-redaction.md) — the row-by-row redaction contract, verified against the code
- [What to Commit](documentation/what-to-commit.md) — which generated files are CI artifacts, and which (if any) are reviewed baselines
- [Troubleshooting](documentation/troubleshooting.md) — symptom → cause → fix for the failure modes people actually hit
- [pytest Guide](documentation/guides/pytest.md) · [FastAPI/ASGI Guide](documentation/guides/fastapi-asgi.md) · [OpenTelemetry Guide](documentation/guides/opentelemetry.md) · [Logging Guide](documentation/guides/logging.md) · [Clarity Guide](documentation/guides/clarity.md)
- [Feature Guide](documentation/feature-guide.md) — every feature this runtime ships, with tier and status
- [Complete Reference (`llms-full.md`)](documentation/llms-full.md) — every guide, one file; [`llms.txt`](documentation/llms.txt) is the machine-readable index for AI agents

## FAQ

### How much overhead does this add, and what happens under high concurrency?

We will not claim "zero overhead" — and unlike some other runtimes in this family, we do not yet have dated, published numbers to cite for this one. A starter benchmark suite exists (`packages/narrativetrace/tests/test_bench_*.py`, run with `uv run poe bench`) covering capture overhead per tracing level, a call through `trace_object` against a direct call, rendering to each format, and the redaction check on a hot path — but `uv run poe bench-gate` only compares a run against the previous run on the *same* machine (host-baseline numbers are not comparable across machines), so this is a nightly regression habit, not a public number yet. Do not assume the Java or TypeScript numbers transfer to this runtime: what a line of tracing code costs is different per runtime. Run `uv run poe bench` yourself against your own hardware if you need a number today — we would rather say nothing here than say something we can't stand behind.

What we can say with confidence is the mechanism. Capture is gated by a tracing level checked *before* any rendering happens: set `NARRATIVETRACE_LEVEL=OFF` and `enter_method` returns `None` immediately — no reflection, no string work, before your arguments are even touched. For hot loops, narrow the traced scope or drop the level rather than tracing everything.

Under concurrency, the two paths of the default `DualPathPipeline` carry different guarantees. A synchronous listener — `LoggingTraceConsumer`, the stdlib-`logging` bridge (this runtime's analog of Java's `Slf4jTraceEventListener`) — runs inline if you attach one, so it is exactly as durable, and costs exactly what, a log call already does. The buffered, best-effort path is a fixed-size ring (65,536 events, never grows) that sheds under load rather than blocking the caller, and every loss is **counted**, never silent — `dropped_count()` sums subscriber backpressure, buffer overwrites, and shedding together, and a run that lost events prints the count on its own `Incomplete:` suite-footer line.

**The honest gap:** there is no sampling in this runtime, or in any NarrativeTrace runtime, today — every traced call is captured in full at its configured level. A percentage- or rate-based sampler is on the roadmap, not shipped. If you need to cap capture volume now, use `NARRATIVETRACE_LEVEL=OFF` or narrow the traced scope to the boundary that matters.

### How do I know a parameter with PII or credentials won't leak into a trace?

Four independent layers, not one blanket promise — the row-by-row contract, verified against the code, is [Privacy and Redaction](documentation/privacy-and-redaction.md):

1. **`@not_traced("password", "cvv")` on named parameters**, and **`not_traced_field(...)`/`__nt_not_traced__` on a class's fields** — explicit redaction you control.
2. **An always-on, multilingual name deny-list** — matches field and parameter names against English, Spanish, Portuguese, French, German and Chinese patterns for passwords, tokens, national IDs and the like, with no locale to select and nothing to opt into.
3. **Value-shape matching, independent of the field name** — a JWT-shaped string, a Luhn-valid card number, a `Set-Cookie`-shaped value, or a national-ID checksum or structural rule (Chilean RUT, Brazilian CPF/CNPJ, Spanish DNI/NIE, French NIR, Chinese resident ID, US SSN) is redacted even under an innocuous name like `data` or `value` — combined in `is_secret_shaped`.
4. **No value-free structural mode yet in this runtime.** The Java sibling's `.nt`/`.approved.nt` format — the categorical guarantee for a context where no value may ever leave the process — is planned here, not shipped (see the [Feature Guide](documentation/feature-guide.md)). Don't confuse this with `TraceTranslationView`: that's a real, shipped feature, but it re-glosses identifier *names* into another language via a glossary — values still pass through byte-identical and untouched, so it is not a value-free mode.

There is also no configurable path-based redaction rule set — no "always redact `user.creditCard`" JSONPath-style policy. Redaction is name- and shape-based, and it is applied at every segment when a `{param.property}` narration template resolves a path, not a data-flow analysis. Be precise about the boundary: layers 1–3 are heuristic and extensible — they can always miss a shape or name nobody has thought to add yet. None of them is *categorical* the way the (not-yet-shipped) structural mode would be. If your threat model requires "no value can possibly leave the process," that guarantee does not exist in this runtime today.

### Can trace IDs correlate with a standard correlation ID across services, or is tracing local only?

Yes — through W3C `traceparent`, the same mechanism OpenTelemetry uses, and both directions ship. **Inbound:** the ASGI middleware (`NarrativeTraceMiddleware`, `adopt_traceparent=True` by default) parses an inbound `traceparent` header and calls `context.adopt_trace_id(...)` — NarrativeTrace's own `trace_id` **becomes** that header's trace id directly, not a separate identifier merely shaped to match. **Outbound:** `attach_traceparent`/`attach_traceparent_async` are `httpx` event hooks that stamp the current context's trace id onto every outgoing request (`packages/narrativetrace-asgi`) — an outbound mechanism the Java runtime doesn't have a counterpart for. Where no header is present, a fresh id is generated in the same W3C 32-lowercase-hex-character shape (`TraceId` is typed as exactly that format). The `narrativetrace-otel` package additionally exports NarrativeTrace spans (`OtelTraceEventListener`, live; `TraceSpanExporter`, batch) with typed `narrative.*` attributes and orphan eviction, so your existing OTel collector, Jaeger, or correlation-id middleware understands the id with nothing to reconcile.

What stays local: the narrative tree itself — the nested method calls, arguments, narration — is captured per process and never shipped to another service; only the trace id crosses the boundary. A downstream service produces its own narrative tree correlated to that same id, not one merged cross-service tree. (There is no worked multi-service example in `examples/` yet exercising this end to end — the mechanism is unit-tested, in `packages/narrativetrace-asgi/tests/test_outbound.py` and the middleware's own tests, not demoed as a running distributed scenario.)

## Examples and demo

Runnable, tested tutorials live under [`examples/`](examples) — see
[`examples/README.md`](examples/README.md) for the map: `ecommerce` (the flagship: decorators,
failure scenarios, thread-pool fork-join and fire-and-forget), `hotel_booking` (clarity scoring
across naming tiers), `minecraft` (refactored vs. unrefactored, side by side), `library`
(dataclasses that narrate themselves), and `fastapi_service` (the ASGI slice).

## License

NarrativeTrace's API and output format are open standards (Apache 2.0). Its runtime is free and
source-available (BSL 1.1, converting to Apache 2.0 four years after each release). Pro is
commercial.

The distributions in this repository are that runtime: **Business Source License 1.1** (SPDX
`BUSL-1.1`) — the full text is in [`LICENSE`](LICENSE). Production use is granted for any purpose,
including internal use and services you provide to your own customers; the one exclusion is offering
NarrativeTrace itself — or a product or service whose value derives substantially from it — to third
parties as a logging, tracing or code-narrative product or service. Four years after a version is
published, that version converts to the Apache License 2.0.

Documentation prose is CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/); the JSON schema
files are Apache 2.0.

<!-- legal:trademark:begin -->
None of these licenses grant any trademark rights; NarrativeTrace is a trademark of Empower Agile.
<!-- legal:trademark:end -->

### The licence, in plain words

Everything installable from this repository is Business Source License 1.1 today; the JSON
schemas are Apache 2.0 (see schema/README.md).

<!-- legal:plain-words:begin -->
**Free to run.** The runtime is source-available under the Business Source
License 1.1: read it, audit it, patch it, and use it in production at no cost —
including inside the products and services you sell to your own customers.

**One exclusion.** You may not offer NarrativeTrace itself — or a product or
service whose value derives substantially from it — to third parties as a
logging, tracing or code-narrative product or service.

**It opens on a date.** Every release converts to Apache 2.0 four years after it
is published; the exact date is printed in that release's LICENSE.

*This summary is a courtesy, not a licence. The LICENSE file is the only binding
text; where the two differ, the LICENSE governs.*
<!-- legal:plain-words:end -->
