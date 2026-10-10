---
name: add-narrativetrace-clarity
description: "Adds or verifies NarrativeTrace Clarity in a Python project. Use when you want a first naming report, per-element suggestions, or an explicit clarity quality gate. Installs narrativetrace-clarity with uv add --dev, runs the real narrativetrace-clarity scan over the project's packages, checks the report is fresh and scored at least one class, renames what it flags, and re-runs until the gate is clean, preserving any thresholds the project already has. Route tracing itself being broken to narrativetrace-doctor. Say 'add a clarity report to this project', 'run narrativetrace-clarity', 'explain our clarity scores', 'make the clarity gate fail on low scores', or 'which names make this hard to read' to invoke it."
---

# add-narrativetrace-clarity

## 1. Find what to scan and what is already there

```bash
git ls-files '*.py' 'pyproject.toml'
```

**verify:** `git ls-files '*.py' 'pyproject.toml' | uv run python -c 'import sys
sys.exit(0 if sys.stdin.read().split() else 1)
'`

**failure:** the listing is empty — this is not a git checkout, or it tracks no Python. Fix: run from the repository root; with no Python to read there is nothing for clarity to score

## 2. Install the gate as a development dependency

```bash
uv add --dev narrativetrace-clarity
```

**verify:** `uv run narrativetrace-clarity --help`

**failure:** the console script is not found — the dev dependency was added but the environment was not synced. Fix: run `uv sync`, then run the check again

## 3. Scan the packages and check the report is real

```bash
uv run narrativetrace-clarity <source-dir> --output-dir build/narrativetrace
```

**verify:** `uv run python -c 'import json, pathlib, sys, time
root = pathlib.Path("build/narrativetrace")
results = root / "clarity-results.json"
report = root / ("clarity-report" + ".md")
if not results.is_file() or not report.is_file() or not report.stat().st_size:
    sys.exit("no report: the scan wrote nothing (wrong source directory?)")
if time.time() - min(results.stat().st_mtime, report.stat().st_mtime) > 600:
    sys.exit("stale report: it is from an earlier run, not this scan")
try:
    scenarios = json.loads(results.read_text(encoding="utf-8")).get("scenarios")
except (ValueError, AttributeError):
    sys.exit("the results file is not a clarity report")
if not isinstance(scenarios, list) or not scenarios:
    sys.exit("the report scored no class")
'`

**failure:** the scan prints `No classes found` and the check says no report — the directory holds no public class: the scan scores classes, skips names with a leading underscore, and does not score module-level functions. Fix: point it at the package directory that holds the project's classes

**failure:** the scores describe libraries, not the project — the scan walked the project root and so the virtual environment under it. Fix: pass the package directories, never `.`

## 4. Read the report and rename what it flags

**failure:** a flagged name is a domain word the project chose on purpose — the scan scores against its built-in dictionaries unless a glossary is committed. Fix: leave the name and say why; the glossary rule below is the lasting fix

**failure:** a flagged method or parameter is part of a public API — renaming it breaks callers outside this repository. Fix: ask before renaming it, and keep the old name as a deprecated alias if so

## 5. Run the project's tests after the renames

**verify:** `uv run pytest -q`

**failure:** a test fails with a name that no longer exists — a caller, a keyword argument or a string still uses the old name. Fix: search the whole repository for the old name and move every use

## 6. Re-run the gate until it is clean

```bash
uv run narrativetrace-clarity <source-dir> --output-dir build/narrativetrace --min-score <min-score> --max-high-issues <max-high-issues>
```

**verify:** `uv run python -c 'import json, pathlib, sys, time
root = pathlib.Path("build/narrativetrace")
results = root / "clarity-results.json"
report = root / ("clarity-report" + ".md")
if not results.is_file() or not report.is_file() or not report.stat().st_size:
    sys.exit("no report: the scan wrote nothing (wrong source directory?)")
if time.time() - min(results.stat().st_mtime, report.stat().st_mtime) > 600:
    sys.exit("stale report: it is from an earlier run, not this scan")
try:
    scenarios = json.loads(results.read_text(encoding="utf-8")).get("scenarios")
except (ValueError, AttributeError):
    sys.exit("the results file is not a clarity report")
if not isinstance(scenarios, list) or not scenarios:
    sys.exit("the report scored no class")
'`

**failure:** exit 1 naming a class below --min-score, or HIGH issues over the limit — a flagged name is still unclear, or a rename introduced another. Fix: read the new report, rename again, and repeat from the tests

## Always

- Rename in snake_case, whatever case the suggestion's examples use. (the suggestion text shares its wording with the other runtimes, so its examples are camelCase; the idea is the lesson, not the spelling)
- Read both artefacts of every run, not only the exit code. (a scan that found no class exits 0 and leaves the last run's files in place)
- Use the thresholds the project already has, and ask before choosing new ones. (enforcement is a decision the project makes, not a default the skill invents)
- With no thresholds in the project and none requested, re-run the plain scan and report what is left. (a gate nobody asked for fails a build nobody expected to fail)
- When the project commits a glossary and has narrativetrace-glossary, run the scan through `python -m narrativetrace_glossary.clarity_scan` with the same arguments. (that is the gate that reads the committed vocabulary, so a domain word the project chose on purpose is not flagged as unclear)

## Never

- Never lower or replace a threshold to hide a failure. (a failing gate is evidence about the names; removing the evidence fixes nothing)
- Never call a scan that found nothing a pass. (an exit 0 with no scored class means the wrong directory was scanned, not that the names are clear)
- Never add --warn-only to make the gate go green. (an advisory gate exits 0 whatever it found, so green then proves nothing)
- Never harvest a glossary only to read the existing vocabulary. (the scan reads a committed glossary; creating one is a separate decision that writes to the project)
- Never promise the score a rename will earn. (a rename's score is measured by the next run, and the report may flag more)
