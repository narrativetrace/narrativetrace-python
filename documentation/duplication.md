# Duplication detection

`uv run poe duplication-report` runs [jscpd](https://github.com/kucherenko-ilya/jscpd) — a
Copy/Paste Detector, the JavaScript-ecosystem tool this port uses in place of the Java runtime's
PMD CPD — over the main and test source trees separately and writes a report every commit.
`uv run poe duplication-check` runs the report step, then reads its output and enforces the
duplication ratchet described below; it is part of `poe check`.

jscpd itself is never a dependency of this workspace's own `pyproject.toml` graph — it runs
through `npx jscpd@<pinned version>`, the same "run through the runtime's own toolchain, `npx`
elsewhere" rule every NarrativeTrace runtime's duplication tooling follows. The pinned version
lives in one place, `scripts/duplication_report.py`'s `JSCPD_VERSION`; this document points back
there rather than keeping its own copy.

## What is measured

- **Language:** Python only, today (see the family-wide schema below).
- **Token floor: 60.** A match below 60 tokens is usually a coincidence — two unrelated
  functions that happen to share a short, common shape — not a structural copy worth acting on.
  Configured as `--min-tokens 60`.
- **Identifiers and literals are ignored.** jscpd is invoked with `--ignore-identifiers
  --ignore-literals` (not `--mode strict`, which is a different axis — comment-skipping, not
  identifier/literal equivalence). With both flags, jscpd then finds *structural* duplication
  (the same shape with different names and values), not merely pasted text with the same names.
  Proven with a fixture pair that differs only in names and literals — everything but shape:

  ```python
  # a.py                              # b.py
  def score_alpha(items):             def score_beta(values):
      n = 12                              limit = 30
      total = len(items)                  total = len(values)
      ratio = total / n                   ratio = total / limit
      return ratio                        return ratio
  ```

  `npx jscpd@5.2.0 --min-tokens 5 --min-lines 3 --ignore-identifiers --ignore-literals --format
  python --reporters console a.py b.py` (a lower floor than this repo's 60, since the fixture
  itself is short) reports **1 clone, 4 duplicated lines, 22 tokens** (labelled `(python,
  renamed)` — jscpd's own term for a structural match under renaming); the identical run with
  both flags dropped reports **0 clones** — the same two files, the only variables being those
  two flags.
- **Main and test sources are scanned separately.** Main = every `packages/*/src` directory;
  test = every `packages/*/tests` directory, plus `examples/` — two separate jscpd invocations,
  mirroring the Java runtime's separate CPD passes over `src/main/java` and `src/test/java`. The
  test tree is reported — its numbers are in `duplication.json` and the summary line — but it
  never gates `duplication-check`. Test scaffolding legitimately repeats (setup, fixture
  builders, assertion blocks); a fixed threshold there would be noise, not signal.

## The ratchet, not a fixed percentage

A single "fail above N%" number is the wrong instrument: the right number depends on the token
floor and on how much of the tree is naturally repetitive (data tables, generated code), so a
fixed threshold ends up either loose enough to never fire or tight enough to block unrelated
work. Instead, `duplication-check` ratchets against a committed baseline,
`config/duplication/baseline.properties`:

- **Fails when the main-tree percentage rises more than 0.3 percentage points above the
  recorded baseline** — a small tolerance that absorbs scan-to-scan noise, not real growth.
- **Fails when a non-exempt cluster is larger than the baseline's recorded largest cluster** —
  a single new large duplicate block is a finding on its own, even while the overall percentage
  stays flat.
- **The test tree never fails the check**, whatever its percentage.

Lower the baseline with the same commit that removes the duplication it recorded. Never raise it
to make a failure go away — add a reasoned exemption instead (below), or leave the finding for a
later pass.

`recorded`/`commit` in `baseline.properties` are free-text markers, never commit SHAs: a hash
pins the baseline to a specific tree that later moves, where a date/marker string does not
invite that reading.

## Exemptions are data

`config/duplication/exemptions.txt` lists deliberate duplication: code that is intentionally
structured as two parallel copies rather than one shared abstraction. Each entry is a `globA ::
globB` pair (matched against the repository-root-relative path jscpd reports, using this port's
own restricted glob syntax — see `scripts/duplication_check.py`'s `matches_glob`: `*` within one
path segment, `**` across segments, `?` for one character; no character classes or brace groups)
with a `# reason` line directly above it. A cluster is exempt only when *every* one of its
occurrences matches one of the pair's two globs — a default-deny rule, so an unclassified cluster
over the floor is always a finding, never a silent pass. A pair with no reason above it, or a
malformed pair, fails the build outright rather than being ignored.

Four pairs are exempt today:

- `packages/narrativetrace/src/narrativetrace/rendering.py ::
  packages/narrativetrace/src/narrativetrace/rendering.py` — the text channel (`render`) and the
  typed channel (`render_structured`) are produced independently on purpose (the module's own
  docstring: "the string case checks the shape once here and reuses it for both the text and
  structured renderings below, rather than letting each re-derive it independently"). Mirrors the
  Java runtime's own `ValueRenderer.java` exemption for the identical pattern.
- `packages/narrativetrace-clarity/src/narrativetrace_clarity/_*_data.py ::
  packages/narrativetrace-clarity/src/narrativetrace_clarity/_*_data.py` — the clarity package's
  `_abbreviations_data.py`, `_collocations_data.py`, `_role_suffixes_data.py` and `_verbs_data.py`
  modules hold nothing but word-list/lookup literals; with literals ignored every row matches
  every other row. Their accessor modules (`abbreviations.py`, `collocations.py`,
  `role_suffixes.py`, `verbs.py`, `generic_tokens.py` — no `_data` suffix) are **not** covered by
  this pair and stay findings, even where one of them (`generic_tokens.py`) also holds its own
  literal word lists alongside real scoring logic.
- `packages/narrativetrace/src/narrativetrace/canonical.py ::
  packages/narrativetrace/src/narrativetrace/canonical.py` — `CanonicalEntry`'s own docstring
  says every field added by schema 1.1/1.2 is "nullable and additive": an intentionally wide,
  flat record, so its field declarations and its attribute-to-schema-key `_FIELD_ORDER` table are
  many structurally-identical single lines once identifiers/literals are ignored. Mirrors the
  Java runtime's own `CanonicalEntry.java` Builder exemption for the identical "one field per
  schema component is the public shape" reasoning.
- `packages/narrativetrace/src/narrativetrace/canonical.py ::
  packages/narrativetrace/src/narrativetrace/span.py` — `CanonicalEntry`'s and `SpanContext`'s
  field declarations match each other once identifiers are ignored, the same wide-record shape
  across the core module's two identity records (`span.py`'s own docstring: "The Java builder is
  replaced by keyword construction plus `dataclasses.replace`"). Mirrors the Java runtime's own
  `CanonicalEntry.java`/`SpanContext.java` cross-file exemption.

`packages/narrativetrace-clarity/src/narrativetrace_clarity/generic_tokens.py`'s own duplication
between its `_MEANINGLESS_PLACEHOLDERS`/`_VAGUE_WORDS` word-list sections is deliberately **not**
exempted — unlike the `_*_data.py` modules, this file also holds real scoring logic (`detect`,
`Tier`), so a path-based exemption for it would mask logic duplication along with data. It is
`main.largestCluster`'s value today.

## Reading the report

`build/reports/duplication/duplication.json` is the normalised result:

```json
{"tool":"jscpd","toolVersion":"5.2.0","language":"python","minTokens":60,
 "main":{"linesTotal":N,"linesDuplicated":N,"percent":x.y,
         "clusters":[{"tokens":N,"lines":N,
                       "occurrences":[{"file":"…","startLine":N,"endLine":N}]}]},
 "test":{"...":"same shape"}}
```

The console prints one summary line per run:

```
duplication: main 13.0% of lines in 68 clusters (largest 1488 tokens
packages/narrativetrace-clarity/src/narrativetrace_clarity/_abbreviations_data.py:5 ↔
packages/narrativetrace-clarity/src/narrativetrace_clarity/_abbreviations_data.py:6) · test 11.0%
in 190 clusters (reported, not gated)
```

(The summary line's "largest" names the largest cluster overall, exempt or not — the same
convention the Java runtime's own summary line uses; `main.largestCluster` in the baseline is
the largest *non-exempt* one, which is a different, usually smaller, number.)

Every duplication run also records `build/reports/duplication/jscpd.status` as `ran-clean` or
`skipped: <reason>` (see "CI" below) — a missing file reads back as `never-ran`, so "ran clean"
and "never ran" stay distinguishable after the fact, the same three-state contract
`scripts/run_security_tool.py` (security scanners) and `scripts/quality_gate_status.py`
(pre-commit format/lint) already use for their own concerns.

## Where this differs from the Java runtime

The Java runtime's tool (PMD CPD) and this port's tool (jscpd) expose different data, so two
things map differently — each is a deliberate substitution, not an oversight:

- **The union unit is lines, not tokens.** CPD exposes a cross-file token index (one running
  count across the whole tokenized corpus), which lets `main.percent` union duplicated *token*
  positions without double-counting overlapping matches. jscpd exposes only per-file line ranges
  for each clone — no cross-file token index — so this port unions duplicated *line* positions
  per file instead (`scripts.duplication_report.covered_line_count`/`union_duplicated_lines`),
  summed across files. The failure it guards against is identical either way: a data-table file
  where every row structurally matches every other row produces dozens of overlapping matches
  over nearly the same span, and naively summing every occurrence's own line span (both sides of
  every clone pair, never deduplicated) multiplies that far past the file's own size.
  `minTokens`/`tokens` still describe jscpd's own clone-detection floor and each cluster's exact
  token count — only the *aggregate percentage's* unit changes, from tokens to lines.
  `main.percent` can therefore never exceed 100%, same guarantee as the Java runtime's, different
  unit underneath it.
- **Clusters are pairs, not arbitrary-arity matches.** CPD's `Match` can hold any number of
  occurrences; jscpd always reports exactly two (`firstFile`/`secondFile`) per `duplicates[]`
  entry, splitting an N-way copy into `N choose 2` pairwise entries instead. Exemption matching
  works unchanged either way (`is_exempt` already only requires every occurrence in *one*
  cluster's list to match), but the raw entry count for a busy data table between three or more
  files runs higher on this port than an equivalent Java scan would report, for the same
  underlying duplication.

There is no PMD-CPD-XML equivalent alongside `duplication.json` for this port — jscpd's own
`--reporters json` output is the only raw format read, and this port keeps only its own
normalised JSON, not the tool's raw file.

This document is intentionally English-only, not part of `documentation/i18n/manifest.json`: it
is an internal build/tooling record, the same category `documentation/README.md` already gives
`security-testing.md`, `security-tooling.md` and `concurrency-stress.md` ("Engineering-only
documents ... are English-only by convention", `documentation/LEAME.md`'s own wording for the
same rule) — this page follows that existing convention rather than gaining a translation
obligation the Java source it mirrors never had either.

## Adding an exemption

1. Run `uv run poe duplication-report` and find the cluster in `duplication.json` or the summary
   line.
2. Confirm it is deliberate — a genuine parallel structure kept apart on purpose, not
   duplication nobody has gotten around to removing.
3. Add a `# reason` line and a `globA :: globB` pair to `config/duplication/exemptions.txt`.
4. Re-run `uv run poe duplication-check` to confirm it passes.

## Lowering the baseline

Remove the duplication, run `uv run poe duplication-report`, and update `main.percent` /
`main.largestCluster` in `config/duplication/baseline.properties` to the newly measured numbers
in the same commit — the same "floored to measured" idiom this build already uses for coverage
and mutation-score floors.

## CI

`poe check` calls `poe duplication-check` (which calls `poe duplication-report` first) on every
run — local, CI push/PR, and scheduled pipelines alike. GitLab's `build` job carries no `rules:`
restriction, so it runs on every pipeline source including `schedule`; that single per-commit
call is therefore also this port's nightly/scheduled JSON producer — no separate job exists, or
is needed, to keep `duplication.json` fresh for a later resolver pass (out of scope for this
document).

Node.js is missing from the `ghcr.io/astral-sh/uv:python3.12-bookworm` image both CI configs use
(verified by hand, 2026-09-12: a fresh container has no `node` on `PATH`) — the CI configuration's
`build` job and `.github/workflows/ci.yml`'s `check` job both run `scripts/install-node.sh`
before `poe check`. The (private, host-run) publish-verify pipeline
(`scripts/publish-public.sh --verify`) runs `poe check` directly on the machine driving the
publish, not in this container image, and that machine already has Node — no install step needed
there.

A machine that skips the install step (a local run with no Node, and no `CI`/
`NARRATIVETRACE_DUPLICATION_REQUIRED=true` set) gets the same graceful-skip contract as
gitleaks/OSV-Scanner/ruff (`scripts/run_security_tool.py`, `scripts/quality_gate_status.py`): a
loud warning and a still-green local build, but a hard CI failure — the rule that a skipped scan
is never silently indistinguishable from a clean one.
