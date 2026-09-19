# Concurrency stress testing

The dual-path pipeline — the synchronous listener path, the buffered asynchronous path, the ring
buffer (`BoundedEventBuffer`), and the event store (`EventStore`) — plus the adoption/live-child/
reset machinery in `context.py` (`_TraceStack`, `ContextVarNarrativeContext`) is the core of this
project and the part most exposed to real concurrent load: every traced method call and every
async hand-off goes through it.

This core is stress-tested by holding it to the same **invariants** every NarrativeTrace runtime
owes, per the shared rule: *"A runtime that cannot yet run a scenario still owes the invariant."*
CPython has no exhaustive bytecode-level interleaving scheduler, so this suite proves the
invariants directly, through high-repetition concurrent stress (see Technique, below) rather than
exhaustive schedule exploration.

## The invariants

| # | Invariant | Java test class(es) | Python test(s) |
|---|---|---|---|
| 1 | Loss accounting is exact: delivered + shed == published, under any interleaving; no event both counted-as-shed and delivered | `LossAccountingTest`, `SaturatedRingAccountingTest`, `ClaimUniquenessTest`, `ConcurrentProducersTest` | `test_pipeline_stress.py::TestLossAccountingExact` |
| 2 | No torn/partial reads: a drain or snapshot sees prefix-consistent state, never a half-written slot or a partially visible append | `EventStoreSnapshotTest`, `DrainRacingPublishTest`, `OverwriteWindowTest` | `test_pipeline_stress.py::TestNoTornReads` |
| 3 | Lazy ring allocation races allocate exactly once | `UnsafePublicationTest` (nearest analogue) | **N/A** — see below |
| 4 | The tail is never stranded: a publish into an empty buffer around the drain's stop/park moment is always eventually drained | `ConsumerParkWakeupTest` | `test_pipeline_stress.py::TestTailNeverStranded` |
| 5 | close()/dispose() racing publish and flush: idempotent, nothing silently lost uncounted, the drain mechanism terminates | `CloseIdempotenceTest`, `CloseRacingFlushTest`, `CloseRacingPublishTest` | `test_pipeline_stress.py::TestCloseRacingPublishAndFlush` |
| 6 | flush()'s post-condition holds under concurrent publish: everything published-before is in the store after | `FlushRacingPublishTest` | `test_pipeline_stress.py::TestFlushPostConditionUnderConcurrentPublish` |
| 7 | The adoption seams under concurrency: capture racing scope-close sees spans through exactly one side; no partial batch adoption at the ceiling; reset racing publish is safe | `AdoptionCeilingTest`, `LiveChildHandOverTest`, `ResetRacingRequestsTest` | `test_context_stress.py::TestAdoptionCeilingAllOrNothing`, `TestLiveChildHandOver`, `TestResetRacingPublish` |

**Invariant 3 is structurally N/A for this runtime.** Neither `BoundedEventBuffer`
(`pipeline/bounded_buffer.py:31-34`) nor `BufferedEventConsumer`
(`pipeline/buffered_consumer.py:80-105`) allocate anything lazily — the ring, the store, and the
drain thread are all built eagerly inside `__init__`, before the constructed object is ever handed
to a caller who could race a second thread against it. There is no "does the first publish race the
allocation?" question to ask of this design. The nearest analogue makes the identical substitution
in `UnsafePublicationTest`'s own doc comment (safe *publication* of an eagerly-built object, not
lazy allocation) — its production ring has the same eager-construction shape.

## Platform mapping

This runtime covers **asyncio tasks** in addition to threads, since asyncio
task interleaving at the adoption/live-child seam was untested before this suite existed. A plain
synchronous call with no `await` inside it (`_TraceStack.adopt`) cannot genuinely race under
asyncio's cooperative model — one coroutine always runs it to completion before another starts —
so invariant 7's adoption-ceiling half is thread-only by construction; the live-child hand-over and
reset-racing-publish halves both span real `await` points and get both a `test_threads` and a
`test_asyncio_tasks` variant, exercising the identical assertion against the identical production
code path, just scheduled cooperatively instead of preemptively.

Technique, since CPython has no exhaustive-interleaving scheduler:

* **Threads** — `threading.Barrier`-synchronised starts (`stress_support.run_barrier_synced`) so
  every repetition hits the same contention window, with `sys.setswitchinterval` lowered
  (`stress_support.narrowed_switch_interval`) so the GIL preempts far more often than its 5ms
  default — combined with high repetition counts rather than exhaustive schedule exploration.
* **asyncio** — adversarial task orderings via explicit yield points (`await asyncio.sleep(0)`,
  `asyncio.Event`) inserted at the seams that matter, run concurrently with `asyncio.gather`/
  `asyncio.ensure_future`, repeated many times.

## Two modes

| Mode | What it is | When it runs | Cost |
|---|---|---|---|
| **Quick (seeded)** | A small, fixed-seed repetition count — a regression net, not a search | every `poe check` (`poe stress-quick`) | seconds |
| **Long (randomised)** | A much larger, randomly-seeded repetition count — the actual search | a scheduled/web `stress` job (`poe stress`) in the private CI config | ~10-60s at the current budget |

```bash
uv run poe check                                                                  # quick mode, part of the full gate
uv run pytest -m stress packages/narrativetrace/tests/test_pipeline_stress.py \
    packages/narrativetrace/tests/test_context_stress.py                         # the suite on its own, quick mode
uv run poe stress                                                                 # long randomised sweep
```

The concurrency stress suite is excluded from the default `pytest`/`poe test`/`poe coverage` run
(`-m "not stress"` in `addopts`) — high-repetition, timing-sensitive tests do not belong in the
coverage-instrumented default suite, matching this repo's existing `poe fuzz`/`poe mutate` cadence
rule: expensive/probabilistic verification lives in its own `poe` task, invoked on its own cadence,
never gating an ordinary commit by itself. The seed is included in `stress_support.stress_seed()`
so a failure the long sweep finds once can be reproduced afterward.

## Package layout

| File | Role |
|---|---|
| `tests/stress_support.py` | shared harness: quick/long repetition budget, seed, `narrowed_switch_interval`, `run_barrier_synced` |
| `tests/test_pipeline_stress.py` | invariants 1, 2, 4, 5, 6 — the ring, the buffered consumer, the event store |
| `tests/test_context_stress.py` | invariant 7 — the adoption ceiling, live-child hand-over, reset racing publish |

## Findings

The running ledger (one row per finding, invariant → verdict) is tracked in the
private backlog; this runtime's private working notes carry the narrative summary of this run.

## What this suite does not do

This suite doesn't replace deterministic unit tests for the same components
(`test_pipeline_buffered.py`, `test_trace_stack_live_child.py`, etc. still own the example-based
and boundary-condition coverage), doesn't measure throughput or latency, and doesn't cover
framework integrations (`narrativetrace-asgi`, `narrativetrace-otel`) beyond the core pipeline they
sit on top of.
