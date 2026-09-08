# Clarity

Because the trace *is* your names, `narrativetrace-clarity` scores naming quality objectively and
can fail CI when names drift.

## Scoring a trace

```python
from narrativetrace_clarity import analyze

result = analyze(context.capture_trace())
print(result.overall_score)          # 0.0 (poor) … 1.0 (excellent)
for issue in result.issues:          # ranked by impact
    print(issue.severity.name, issue.category, issue.element, "→", issue.suggestion)
```

Five weighted dimensions: method names (0.30), class names (0.20), parameter names (0.25),
structural (0.15), cohesion (0.10). Scores draw on byte-identical dictionaries shared across the
NarrativeTrace runtimes:
1053 verbs across 34 domain categories, 187 abbreviations, 35 collocation maps, and role suffixes.

Issues are score-band classified (HIGH ≤ 0.20, MEDIUM ≤ 0.50), deduplicated by
`category|element` with summed occurrences, and ranked by impact.

## Your own vocabulary, from the glossary you already have

The built-in dictionaries know general software English. They do not know that `fold` is a verb in
your domain, that `tranche` is a precise noun, or that `fx` is shorthand your team has accepted —
and a name they do not know scores as unknown, not as domain-specific.

You teach them with the vocabulary file your repository already carries: the committed
`glossary.json` (ADR-012). There is no second dictionary file to keep in sync.

| Glossary entry | Kind | What clarity learns |
|---|---|---|
| `settle trade` | `verb-phrase` | `settle` is a domain verb; `trade` is a domain noun |
| `credit tranche` | `noun-phrase` | `credit` and `tranche` are domain nouns |
| `fx` | `word` | `fx` is a domain noun |

Multi-word terms teach one token at a time, because identifiers are scored one token at a time.
Every bounded context contributes: an identifier carries no module path, so context scoping cannot
apply at scoring time.

### Accepted shorthand is its own section

Which abbreviations your project accepts is a separate decision from which words its domain uses,
so it lives in its own root-level section of `glossary.json` (schema 2):

```json
{
  "schemaVersion": 2,
  "contexts": { "trading": { "packages": ["acme.trading"] } },
  "abbreviations": { "fx": "foreign exchange", "calc": "calculate" },
  "terms": []
}
```

A token listed there is never asked to be spelled out. A token that merely *appears inside* a
committed term is not: committing the noun phrase `calc total` teaches that `calc` and `total` are
domain nouns, and says nothing about whether `calc` is accepted shorthand — so the
`calc` → `calculate` hint survives for the rest of the repository.

The section is human-owned: harvesting never writes it, and merging a harvest carries it through
untouched. A glossary that declares none is stamped `"schemaVersion": 1` and writes exactly the
bytes it wrote before the section existed, so adopting the feature costs no diff churn. Readers
accept the section at any schema version.

The built-in dictionaries keep their authority. A project can teach the scorers a word they do not
know; it cannot overrule a word they do — generic verbs (`process`, `handle`) and boolean prefixes
(`is`, `has`) stay where they are, meaningless placeholders (`temp`, `foo`) are not rescued by
being written down, and deprecated synonyms, `template` entries and `stale` terms are never
vocabulary. Only the *committed* file counts: nothing a run harvests feeds back into that same
run's scores, which would make them non-deterministic and self-certifying.

```python
from narrativetrace_clarity import analyze
from narrativetrace_glossary import read_project_vocabulary

result = analyze(context.capture_trace(), read_project_vocabulary("."))
```

The pytest plugin does this for you, once per session: `narrativetrace.glossary_dir` (env
`NARRATIVETRACE_GLOSSARY_DIR`) names the directory, defaulting to the working directory. Reading is
unconditional — it changes nothing on disk — and a glossary that cannot be read degrades to the
built-in dictionaries with a warning rather than failing the suite.

## The CI gate

The `narrativetrace-clarity` console script scans Python sources (each public method is a
depth-1 root) and writes `clarity-results.json` + `clarity-report.md`:

```bash
narrativetrace-clarity src --min-score 0.5 --max-high-issues 0 --output-dir build/narrativetrace
# --format both|md|json   --warn-only   (unknown format → exit 2; below threshold → exit 1)
```

In this repo it is wired into `uv run poe check` via the `clarity` task.

## Runtime aggregation

The pytest plugin scores each test's captured tree, prints a `Clarity: X% high | …` footer, and
(with output enabled) aggregates one `clarity-results.json` entry per traced test.
