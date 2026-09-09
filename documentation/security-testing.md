# Security testing

See also [`documentation/security-tooling.md`](security-tooling.md) for the other half of
"security" — secrets scanning, static analysis, and dependency-vulnerability scanning of the
repository itself, as opposed to this document's fuzzing of NarrativeTrace's own input handling.

NarrativeTrace reads input it does not control. Wire headers arrive from strangers, the value
renderer walks arbitrary object graphs eagerly (including third-party objects whose `__repr__`/
`__str__` can throw, recurse or block), and — above all — the narrative it writes is read by a
language model as often as by a person.

This document describes the suite that attacks all of that on purpose:
`packages/narrativetrace-security-tests`, a test-only package that depends on every distribution
which renders or emits, so one assertion can reach the whole output surface. It carries the same
targets and the same hostile corpus as every other NarrativeTrace runtime; the Java runtime's
`narrativetrace-security-tests` module is the sibling suite, and its own security-testing document
sits beside it.

Two tiers:

| Tier | What it is | When it runs | Cost |
|---|---|---|---|
| **A — structured fuzz** | Hypothesis properties fed by the shared hostile corpus | every `poe check`/`poe test` | seconds |
| **B — coverage-guided fuzz** | real atheris fuzz of target 1 on x86_64 Linux; a budgeted Hypothesis run on both targets everywhere/always (see below) | a separate `poe fuzz` task | ~60s (atheris) + ~60s (Hypothesis) at the current budgets |

**Every NarrativeTrace runtime mirrors the same corpus.** `tests/resources/hostile-corpus/` is copied
byte-identical from the shared master copy's `narrativetrace-security-tests/src/test/resources/
hostile-corpus/` — data, not code, so a newly-understood attack shape lands once and every runtime
inherits it on the next sync. Only the corpus reader (`hostile_corpus.py`) and the object-graph
builder (`hostile_graphs.py`) are written per language.

## Running it

```bash
uv run poe check                                              # Tier A, part of the full gate
uv run pytest packages/narrativetrace-security-tests/tests    # the suite on its own
uv run poe fuzz                                                # Tier B, budgeted
```

## Package layout

| File | Shared name | Role |
|---|---|---|
| `tests/hostile_corpus.py` | `corpus/HostileCorpus` | reads the five JSON fixtures into typed cases |
| `tests/hostile_graphs.py` | the graph builder in `ValueRendererRedactionPropertyTest` | turns a declarative `graphs.json` shape into a live object graph |
| `tests/emitters.py` | `oracle/Emitters` | every shipped output format, in one map (`EMITTERS`), so an emitter added there is covered by every oracle at once |
| `tests/oracles.py` | `oracle/Oracles` | shared assertions: budget, bounded size, redaction (`contains_nowhere`), idempotence, no-thread-left-behind |
| `tests/formats.py` | the shape half of `oracle/Formats` | JSON/diagram/frontmatter *shape* comparisons for the injection oracle (well-formedness itself lives in the root `conformance.py`) |
| `tests/fuzz_config.py` | `fuzz/FuzzBudget` | Tier B's Hypothesis settings (budget, corpus database) |
| `tests/test_hostile_corpus.py` | `HostileCorpusTest` | pins the corpus fixtures themselves (case counts, ASCII-on-disk, `repeat` materialization) |
| `tests/test_traceparent_properties.py` | `TraceparentParsingPropertyTest` | target 1 |
| `tests/test_value_renderer_redaction_properties.py` | `ValueRendererRedactionPropertyTest` | target 2 |
| `tests/test_output_format_properties.py` | `OutputFormatPropertyTest` | target 3 |
| `tests/test_injection_containment_properties.py` | `InjectionContainmentPropertyTest` | target 7 |
| `tests/test_artifact_naming_properties.py` | `ArtifactNamingPropertyTest` | the writer's other input: the *name*, not the value (2026-09-08) |

The package is excluded from the publish pipeline's package list (it has no `main`-equivalent
source, `src/narrativetrace_security_tests/__init__.py` is empty, and its `pyproject.toml` carries
`Private :: Do Not Upload`) but its *source* ships in the public tree — the same split as the Java
module: excluded from publishing, not from the repository.

## The oracles

A crash is not the only defect, and "it did not throw" is not an oracle. Every target in this
package asserts from this list:

1. **No uncaught exception.** A hostile input degrades — it never propagates.
2. **Bounded time and size.** `oracles.within_budget`/`bounded_size`.
3. **Well-formedness, read back by the consumer's own parser.** JSON validates against the
   canonical `chapter-tree`/`chapter`/`entry` schemas (`conformance.py`); a Mermaid/PlantUML diagram
   carries no raw control character; Markdown frontmatter parses as YAML.
4. **Redaction.** A sentinel planted behind `@not_traced`/a deny-listed name appears in **no**
   output of **any** format, at **any** depth (`oracles.contains_nowhere`).
5. **Idempotence.** Rendering the same input twice produces the same bytes
   (`oracles.idempotent`) — this is why `emitters.py` gives `export_chapter` a fixed clock: its
   timestamp field is intentionally live wall-clock time otherwise.
6. **No thread left behind.** `oracles.no_new_threads`.
7. **AI-consumer containment.** An instruction-shaped value comes back as *exactly one value* when
   the output is parsed again — compared against a benign baseline's document *shape*
   (`formats.json_shape`/`statements_of`/`frontmatter_keys`/`fence_count`), because well-formedness
   alone would happily accept a forged field.

## Tier B: real on x86_64 Linux, a documented Hypothesis fallback everywhere else (verified 2026-09-09)

Java's Tier B is Jazzer, whose `@FuzzTest` steers generation by the target's own coverage. The
Python analogue is [atheris](https://github.com/google/atheris) — Google's libFuzzer-backed
coverage-guided fuzzer for Python. Earlier notes here attributed atheris's unavailability to this
repo's Python floor (`>=3.12`). **That was never the accurate story**: atheris 3.0.0 (2025-11-24)
added Python 3.12/3.13 support and 3.1.0 (2026-06-17) added 3.14, both released before this
correction — the real blocker is **platform/toolchain, not Python version**:

- **PyPI wheels exist only for `manylinux2014_x86_64`** (cp312, cp313, cp314) — confirmed against
  atheris 3.1.0's published file list. There is no macOS wheel at all (`arm64` or `x86_64`) and no
  `aarch64` Linux wheel. Building from source needs a Clang+libFuzzer toolchain.
- **This repo's `.devcontainer` (`aarch64` Linux, `python:3.13-bookworm`)**: no wheel, and no
  `clang` binary anywhere on `$PATH` to build from source (`RuntimeError: Failed to find
  libFuzzer; set either $CLANG_BIN to point to your Clang binary, or $LIBFUZZER_LIB ...`).
- **A macOS `arm64` host**: also no wheel, and this time Clang *is* present (Apple's own) but does
  not ship libFuzzer, a different, more specific failure than the devcontainer's "no clang at
  all" (`RuntimeError: Failed to find libFuzzer; you may be building using Apple Clang. Apple
  Clang does not come with libFuzzer. ...`).
- **A plain `x86_64` Linux CPython 3.12 interpreter DOES work** — verified live 2026-09-09 in a
  `python:3.12-bookworm --platform linux/amd64` container (matching GitHub Actions'
  `ubuntu-latest` and this repo's own GitLab CI image's architecture): `pip install atheris`
  resolves the real manylinux wheel, no Clang/libFuzzer toolchain needed at all.

**A real coverage-guided harness is wired for target 1** (`atheris_traceparent_target.py`,
fuzzing `parse_traceparent`) and **verified actually fuzzing**, not merely importing: a 15-second
run of exactly this harness, in the same verification container, drove coverage from 3 to 28
edges over 70,571 executions (~4,400/sec) starting from an empty corpus — real libFuzzer
`NEW`/`REDUCE` lines, not a smoke test. `scripts/fuzz_report.py` (`poe fuzz`'s entry point) checks
whether `atheris` is importable and, only where it is, runs this harness for a time-boxed 60
seconds, reporting its own execution count and failing the run if throughput falls far below what
a genuine fuzz produces (`AtherisRunReport.is_credible`) — a crash makes libFuzzer itself exit
non-zero, which propagates as this run's failure, exactly as a real finding should. **Target 2**
(`ValueRenderer` over hostile object graphs) has **no** atheris harness yet: its input is an
object graph, not a byte string, so a byte-to-graph decoder is separate, non-trivial work left for
later — the Hypothesis sweep remains its only Tier B coverage. `atheris` itself is wired as an
optional dependency (`security` dependency group, `sys_platform == 'linux' and platform_machine
== 'x86_64'` marker) so `uv sync --group security` installs it for real only where it can
actually resolve a wheel, and attempts nothing (no source build, no error) everywhere else.

**Fallback (every other environment, and target 2 everywhere):** `poe fuzz`
(`scripts/fuzz_report.py`) runs a budgeted plain-Hypothesis sweep (`NARRATIVETRACE_FUZZ=1`, 5,000
examples per property instead of the default 100) over the top two targets, per Java's own
priority table below. This buys **generated-example coverage of the input *shape* space**
(Hypothesis's strategies + shrinker) — it does **not** buy coverage guidance from the target's own
control-flow graph the way the real atheris harness above does: a Hypothesis run can miss a branch
no strategy happens to reach, where a coverage-guided fuzzer would notice the branch went
uncovered and steer generation toward it. `fuzz_config.fuzz_settings` points Hypothesis's example
database at `tests/.fuzz-corpus/`, committed to the repository rather than the default gitignored
`.hypothesis/` cache: a crash `poe fuzz` finds once is saved there and replayed first on every
subsequent `poe test`/`poe check`, so it becomes a permanent regression the whole team inherits —
the role Jazzer's committed seed corpus plays for Java.

`scripts/fuzz_report.py` makes every branch's own honesty checkable: whichever tier ran (real
atheris, the Hypothesis fallback, or both), it parses the actual executions/examples and the
wall-clock duration and fails the task if the total falls below a floor — the exact failure class
the team already caught once for real (`python-fuzz` reporting "OK" in 16 seconds against a
budget that cannot finish that fast): a run that collected zero tests, crashed before generating
anything, or otherwise did nothing while still exiting 0.

The natural next steps, in priority order: (1) confirm the CI runners this repo actually uses are
x86_64 Linux (both the private and public CI configs use images that suggest it, but that has not
been independently confirmed from inside a live CI job); (2) write a byte-to-object-graph decoder
and a real atheris harness for target 2; (3) targets 3/4, to match Java's four. Nothing about the
corpus or the property tests they feed needs to change for any of these.

## The targets

In priority order (mirrors Java's table; targets 5/6 are clarity/config, out of this package's
scope, and are not ported here):

| # | Target | The oracle that matters most | Tier A | Tier B |
|---|---|---|---|---|
| 1 | `parse_traceparent`/`format_traceparent` and any other wire reader | never throws; round-trips what it accepts | ✓ | ✓ |
| 2 | `ValueRenderer` over hostile object graphs | redaction, at any depth, through any container | ✓ | ✓ |
| 3 | Every output format | well-formedness, bounded size | ✓ | — |
| 4 | Template parsing and rendering | a redacted path renders `[REDACTED]` | pinned (see below) | — |
| 7 | Every output format, again | AI-consumer containment | ✓ | — |

Target 4 (template redaction) has no dedicated Tier A property file: the Java finding it exists to
catch (an empty path segment, e.g. `{card.}`) was checked against this runtime and found already safe
— `_resolve_segment`'s `getattr(owner, "")` already raises and is caught, unlike Java's direct
`property.charAt(0)` indexing — so it is pinned with regression tests
(`test_template.py::TestEmptyPathSegment`, `test_redacted_paths.py::TestEmptyPathSegment`) rather
than a new property suite.

## From a crash to a regression test

1. **Reproduce it**, then add a case to the relevant `tests/resources/hostile-corpus/*.json` file
   describing the *shape*, not just the bytes — the generated half of Tier A explores around it,
   and every other runtime inherits it on the next corpus sync.
2. **Fix it in the module that owns it**, with a named unit test there (this package proves the
   property across modules; the owning module's test is what a future reader finds when they
   change that code). See `git log` on `packages/narrativetrace/src/narrativetrace/render/
   frontmatter.py` and `escape.py` for worked examples from this suite's own findings.
3. **Commit the corpus case and the fix together.**
4. **Check whether the finding applies to the other NarrativeTrace runtimes too** (several of this
   runtime's findings did) and report it so the other runtimes can be checked.

## What the suite does not do

- It does not replace the property tests inside each module. Those own their module's behavior;
  this owns the invariants that only hold across modules.
- It does not fuzz third-party libraries, only NarrativeTrace's own readers, renderers and writers.
- It does not assert on the *content* of a narrative, only on its structure and its containment.
