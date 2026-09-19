# FAQ

Answers to the questions that come up often enough to deserve one page, rather than being
re-explained in every guide that touches them.

## Two dials, two paths

**I set the tracing level to `DETAIL` but nothing shows up in my logs. Or: I set my logger to
`WARNING` and the trace still appears in my pytest artifacts. Which setting wins?**

Both, because they answer different questions. NarrativeTrace has two dials, and getting a
captured trace into your logger is a separate step from capturing it at all.

**Dial 1, the tracing level, decides what is captured.** `OFF`, `ERRORS`, `SUMMARY`, `NARRATIVE`,
`DETAIL` — cumulative, each including everything below it (see [Configuration Guide, § Tracing
level](guides/configuration.md#tracing-level)). It is NarrativeTrace's own setting, and it acts at
two different points, not one: at `OFF`, `context.is_active()` is `False` and `trace_object`'s
wrapper skips interception entirely — the wrapped call runs with none of the capture machinery
touched, and nothing becomes an event, for any consumer. From `ERRORS` up, every call *is*
intercepted and recorded — `ERRORS` and `SUMMARY` don't skip interception, they prune the
resulting tree *after* capture (dropping non-error paths, collapsing intermediate frames); only
below `DETAIL` are parameter values left out at capture time, unrecoverable later regardless of
what the logger does. No other setting can bring back what `OFF` skipped or `DETAIL` alone
captures.

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
  tutorial](sixty-seconds.md#send-it-to-your-logger) and every guide in this repository use.
- **Live, as events happen** — attach a `LoggingTraceConsumer` as the synchronous listener of a
  `DualPathPipeline` you assemble yourself, typically alongside a `BufferedEventConsumer` as its
  best-effort path (a bounded ring, 65,536 events by default, load-shedding under pressure, every
  loss counted — see [Concurrency](../README.md#concurrency)) for any other live consumer, an
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

See also: [Configuration Guide](guides/configuration.md) · [Logging Guide](guides/logging.md) ·
[Troubleshooting](troubleshooting.md)
