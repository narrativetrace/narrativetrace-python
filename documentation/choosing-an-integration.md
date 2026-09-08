# Choosing an integration

NarrativeTrace has one capture model — an enter/exit event published through the pipeline — reached
by a small number of attachment mechanisms. This page answers "which package do I actually need,"
first as a lookup table, then as a decision diagram, then with the caveats each path has.

## You want... / Start with...

| You want | Start with |
|---|---|
| Traces in tests, least wiring | `narrativetrace-pytest` (`narrative_trace` fixture) |
| Explicit control over what gets wrapped, in plain Python | `trace_object(obj, context)` — the core, no framework required |
| FastAPI/Starlette request lifecycle | `narrativetrace-asgi` |
| Propagate a trace to a downstream HTTP call | `narrativetrace-asgi`'s `attach_traceparent` (httpx) |
| Traces in your production log stream | `LoggingTraceConsumer` / `NarrativeContextFilter` (core) |
| structlog pipelines | `narrativetrace-structlog` |
| OpenTelemetry spans | `narrativetrace-otel` |
| Sequence diagrams from a captured tree | `narrativetrace-diagrams` |
| Naming-quality CI gate | `narrativetrace-clarity` console script |
| Flask (WSGI) or Django | Not shipped yet — see *Platform ceilings* below |

This is the same matrix the [root README](../README.md#choose-your-integration) carries; it lives
here too as the anchor for the diagram and detail below.

## The decision

There is exactly one capture primitive — `trace_object(obj, context)` — and it wraps any concrete
Python object directly, reflectively, at the instance you pass it. There is no interface or base
class requirement the way a dynamic-proxy-based integration needs one, so the decision is really
about *where* the wrapping happens, not *whether* an object qualifies:

```text
Where do you want traces to start?
   |
   +-- Inside my test suite -----------------> narrativetrace-pytest
   |                                            (narrative_trace fixture; no manual wrapping)
   |
   +-- Around specific objects, plain script
   |   or application code -------------------> trace_object(obj, context) directly (core)
   |
   +-- Across an HTTP request lifecycle
   |     |
   |     +-- FastAPI / Starlette (ASGI) -------> narrativetrace-asgi
   |     +-- Flask / Django -------------------> not shipped yet (see Platform ceilings)
   |
   +-- Alongside code that already runs
       across threads or asyncio tasks --------> trace_object as above, plus a
                                                  context snapshot at the boundary
                                                  (see Cross-thread work below)
```

There is no zero-code, bytecode-level attachment mechanism (no import hook, no `sitecustomize.py`
auto-instrumentation shipped here) — every path above is an explicit call your code makes or a
middleware you register, never something that rewrites classes as they load.

## One thing every path shares

All of the mechanisms above build the same `TraceTree` from the same `TraceEvent` stream —
`trace_object`'s `_TracedProxy`, the pytest fixture, and the ASGI middleware all end up calling
the same context (`ContextVarNarrativeContext.capture_trace()`); none of them define their own
notion of a captured call. Choosing an integration is a question of *how the call gets wrapped*,
never of what gets recorded once it is — every path funnels through that same capture seam by
design, an internal decision (PY-001, PY-004, PY-005) this page does not need to re-litigate.

## Caveats per path

- **`trace_object`** — wraps the instance you pass it; a reference to the *original*, unwrapped
  object bypasses capture entirely, so wrap at the point your code hands the object out (a
  composition root, a factory, a fixture), not after. Every public method (no leading underscore)
  is traced automatically; there is no per-method opt-in list beyond the decorators.
- **`narrativetrace-pytest`** — auto-registers as a pytest plugin; the `narrative_trace` fixture
  gives one context per test, so tracing spanning multiple tests (a session-scoped resource) needs
  its own context, built by hand with `ContextVarNarrativeContext`.
- **ASGI (`narrativetrace-asgi`)** — only HTTP scopes are captured (`scope["type"] == "http"`);
  WebSocket and lifespan scopes pass through untouched. `excluded_paths` matches the request path
  by exact string, not a glob or prefix — `/health` excludes only `/health`, never `/health/live`.
- **Cross-thread / cross-task work** — `ContextVarNarrativeContext` isolates threads *and* asyncio
  tasks by design (each gets its own view). Work submitted to a `ThreadPoolExecutor` or spawned as
  an `asyncio.Task` only joins the parent trace through `ForkJoinGroup`/`FireAndForgetGroup` or a
  context snapshot taken at the boundary — a thread or task that never received one stays isolated,
  and its `captureTrace()`-equivalent call sees only its own work. One known gap: forking directly
  inside an `async def` traced method resolves the parent through the synchronous call stack, which
  is empty there, so children launched that way land as new roots instead of nested under the
  `async` caller — fork from a synchronous method, or from a thread pool, to keep the nesting.
- **`narrativetrace-otel`** — requires `opentelemetry-api>=1.20`; it bridges an already-captured
  `TraceTree` to OTel spans (batch exporter) or listens live — it does not replace OpenTelemetry's
  own SDK/exporter configuration.

## Platform ceilings

Every path above assumes CPython ≥ 3.12. Flask (WSGI) and Django middleware are **planned, not
shipped** — the same request-boundary contract as `narrativetrace-asgi` is the intended shape, but
there is no package to install today; see the [Feature Guide](feature-guide.md) for status. There
is no PyPy or GraalPy compatibility testing.

## Recipes

Every path in the matrix has a worked example under [`examples/`](../examples) (see
[`examples/README.md`](../examples/README.md)) and a guide under [`guides/`](guides) — this page
answers *which*, those answer *how*.
