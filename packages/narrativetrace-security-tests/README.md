# narrativetrace-security-tests

Cross-module hostile-input fuzz suite: the cross-runtime hostile corpus and oracles, shared with
the other NarrativeTrace runtimes. Test-only, matching the Java runtime's
`narrativetrace-security-tests` Gradle module in shape: it depends on the rendering/output surface
of several other distributions so that one assertion (a redacted value must reach no output, an
injection payload must come back as exactly one value) can be proven once across every renderer,
instead of once per renderer.

## Why this is a separate distribution

Java's module has no `src/main` -- it is a test aggregator, nothing depends on it, and it is
excluded from Maven Central publishing, Javadoc aggregation, mutation testing (pitest), and
coverage verification (JaCoCo), while still shipping in the public source-available tree and
running in ordinary CI. This distribution mirrors that shape as closely as Python packaging
allows:

| Java exclusion | Python equivalent here |
|---|---|
| Not in `publishedModules` (no Maven Central publish) | `classifiers = ["Private :: Do Not Upload"]` -- the standard PyPI/twine convention; nothing in this repository runs `uv publish` on it, and it should never be added to one that does |
| Ships in the public GitHub source tree | Ships in the public source tree too -- the corpus and its property tests are exactly what the Java README asks every runtime to carry |
| Excluded from `aggregateJavadoc`, pitest, JaCoCo coverage verification | Not listed in `poe clarity`'s scanned paths, no `[tool.mutmut]` section/`poe mutate-*` task, not in `[tool.coverage.run] source` -- there is no production `src/` logic to score, mutate, or hold to a coverage floor |
| Still compiled and run by `./gradlew check` | Still covered by `poe test`/`poe typecheck` (mypy `--strict`) like every other workspace member -- basic correctness is not exempted, only the metrics that assume a `main` source set |

## Layout

- `tests/resources/hostile-corpus/` -- the five JSON fixture files plus `README.md`, copied
  **byte-identical** from the Java runtime (`narrativetrace-security-tests/src/test/resources/
  hostile-corpus/` there). Never hand-edit; a new case is added once, upstream, and synced here.
- `tests/hostile_corpus.py` -- the corpus reader (the Python form of the shared `HostileCorpus`).
- `tests/hostile_graphs.py` -- turns a declarative graph shape from `graphs.json` into a live
  Python object graph. This is the one piece of the corpus that is legitimately per-runtime (see the
  corpus `README.md`); the mapping from JDK-specific wrapper types (`Optional`, `AtomicReference`,
  `Map.Entry`, ...) this runtime's renderer has no special case for, onto real Python idioms, is
  documented in that module's docstring.
- `tests/oracles.py` -- the shared assertions every property test calls (redaction containment,
  bounded time/size, idempotence, no thread left behind).
- `tests/emitters.py` -- the map of output-format name to render function every oracle iterates.
- `tests/test_*_properties.py` -- one file per Tier A target, each replaying the corpus first and
  then sweeping generated hostile input with Hypothesis.

See `documentation/security-testing.md` at the repository root for the full design (the oracles,
the two tiers, and how a crash becomes a regression test).
