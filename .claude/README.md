# narrativetrace-python

The NarrativeTrace agent skills for Python. This plugin carries 7 skills and nothing else: no hooks, no MCP servers, no executables. Each skill is a page of instructions that Claude follows in your Python project, using your own `uv` and Claude Code's normal permission prompts.

Install it from this repository's marketplace:

```
/plugin marketplace add narrativetrace/narrativetrace-python
/plugin install narrativetrace-python@narrativetrace-python
```

## Skills

- `narrativetrace-doctor`: Diagnoses a NarrativeTrace Python install and configuration.
- `add-narrative-tracing`: Installs NarrativeTrace into a Python project and gets it to a first trace.
- `narrativetrace-feedback`: Reports a defect in NarrativeTrace itself -- the library, the doctor, an agent skill, or the published install prompt.
- `add-narrativetrace-clarity`: Adds or verifies NarrativeTrace Clarity in a Python project.
- `narrativetrace-verify`: Verifies a change in a Python project by reading what the code actually did before saying it is done.
- `narrativetrace-debug`: Finds the cause of a wrong result in a Python project by reading what the code did with the values, not by stepping through it.
- `narrativetrace-explain`: Use when someone asks what an application or a flow actually does, with nothing broken and no change needing verification.

## What the skills run

The plugin pre-approves no command. The first time a skill runs one of these in your project, Claude Code asks you. Every command is listed here exactly as the skills spell it.

- `uv`, to add the NarrativeTrace packages to your project and to bring its environment up to date. `uv add` edits your `pyproject.toml` and `uv.lock`:

```
uv add narrativetrace
uv sync
uv add --dev narrativetrace-clarity
```

- `uv`, to run the NarrativeTrace command line and the two commands the NarrativeTrace packages put in your project. `uv run narrativetrace init --dry-run` only previews an install and writes nothing. `feedback draft` and `feedback url` write the two report files described below, and the Clarity scan writes its report under `build/narrativetrace/`. Applying an install and promoting an approval baseline with `narrativetrace-approve` are separate steps that wait for your yes. Some of these pipe their output into a short `python -c` check that only reads it:

```
uv run narrativetrace doctor || true
uv run narrativetrace doctor --json | uv run python -c 'import json, sys
report = json.load(sys.stdin)
findings = report.get("findings")
sys.exit(1 if not isinstance(findings, list) or len(findings) != 21 else 0)
'
uv run narrativetrace doctor --json | uv run python -c 'import json, sys
report = json.load(sys.stdin)
by_id = {f["id"]: f for f in report["findings"]}
finding = by_id.get("trap.redaction-proof")
sys.exit(1 if finding is None or finding["status"] not in ("pass", "fail") else 0)
'
uv run narrativetrace init --dry-run
uv run narrativetrace doctor --json | uv run python -c 'import json, sys
report = json.load(sys.stdin)
bad = [f for f in report["findings"] if f["id"].startswith("toolchain.") and f["status"] != "pass"]
if bad:
    print(json.dumps(bad))
sys.exit(1 if bad else 0)
'
uv run narrativetrace doctor --json | uv run python -c 'import json, sys
from narrativetrace_tooling.frameworks.table import wiring_check_ids
report = json.load(sys.stdin)
ids = set(wiring_check_ids())
bad = [f for f in report["findings"] if f["id"] in ids and f["status"] != "pass"]
for f in bad:
    print(f["id"] + ": " + f["fix"])
sys.exit(1 if bad else 0)
'
uv run narrativetrace doctor --json | uv run python -c 'import json, sys
report = json.load(sys.stdin)
by_id = {f["id"]: f for f in report["findings"]}
finding = by_id.get("config.service-identity")
if finding is None or finding["status"] != "pass":
    print(finding["fix"] if finding else "the doctor has no config.service-identity finding")
sys.exit(0 if finding is not None and finding["status"] == "pass" else 1)
'
uv run narrativetrace feedback draft --category <category> --step "<where it happened>" --did "<what you did>" --happened "<what happened>" --expected "<what you expected>"
uv run narrativetrace feedback url --category <category> --step "<where it happened>" --did "<what you did>" --happened "<what happened>" --expected "<what you expected>"
uv run narrativetrace feedback url --category <category> --step "<where it happened>" --did "<what you did>" --happened "<what happened>" --expected "<what you expected>" | uv run python -c 'import sys
sys.exit(0 if "/issues/new?template=" in sys.stdin.read() else 1)
'
uv run narrativetrace-clarity <source-dir> --output-dir build/narrativetrace
uv run narrativetrace-clarity <source-dir> --output-dir build/narrativetrace --min-score <min-score> --max-high-issues <max-high-issues>
uv run narrativetrace-clarity --help
uv run narrativetrace-approve
```

- `uv`, to run your own tests and your own scripts, which are your project's code and do what they do. NarrativeTrace writes its trace files under `narrative-traces/` and, in approval mode, `test-narratives/` as they run:

```
uv run python main.py
uv run python main_with_logger.py
uv run pytest -q
uv run pytest <the smallest test that drives the real path>
uv run pytest || true
uv run pytest
uv run pytest <the test that reproduces the symptom>
uv run pytest <the test that exercises the flow you were asked about>
```

- `uv run python -c`, short scripts that read files in your project and print them or check them, and change nothing:

```
uv run python -c 'print(
    "Render a call with a deny-listed parameter name (e.g. password or token) in a test and "
    "assert the output contains [REDACTED], and that a neighboring non-sensitive value is still "
    "present."
)
'
uv run python -c 'import pathlib
root = pathlib.Path("narrative-traces")
files = sorted(root.rglob("*.md"), key=lambda p: p.stat().st_mtime) if root.is_dir() else []
if not files:
    print("no rendered .md file found yet under narrative-traces -- run your tests or app once")
else:
    newest = files[-1]
    print(newest)
    print(newest.read_text(encoding="utf-8"))
'
uv run python -c 'import pathlib
root = pathlib.Path("test-narratives")
received = sorted(root.rglob("*.received.nt")) if root.is_dir() else []
if not received:
    print("no approval traces configured yet under test-narratives -- nothing pending")
else:
    newest = received[-1]
    approved = newest.with_name(newest.name.replace(".received.nt", ".approved.nt"))
    print("received: " + str(newest))
    if approved.is_file():
        print("approved: " + str(approved))
        print(approved.read_text(encoding="utf-8"))
        print("--- vs received ---")
    else:
        print("no .approved.nt yet -- first approval, review then promote")
    print(newest.read_text(encoding="utf-8"))
'
uv run python -c 'import pathlib, subprocess, sys
result = subprocess.run(
    ["uv", "run", "narrativetrace", "init", "--dry-run"], capture_output=True, text=True
)
shown = (
    "action(s)" in result.stdout
    and ".agents/skills" in result.stdout
    and "AGENTS.md" in result.stdout
)
untouched = not pathlib.Path(".agents/skills").exists() and not pathlib.Path("AGENTS.md").exists()
sys.exit(0 if result.returncode == 0 and shown and untouched else 1)
'
uv run python -c 'import pathlib
draft = pathlib.Path("build/narrativetrace/feedback") / ("feedback-draft" + ".md")
print(draft.read_text(encoding="utf-8"))
'
uv run python -c 'import pathlib, sys
root = pathlib.Path("build/narrativetrace/feedback")
paths = [root / (stem + ".md") for stem in ("feedback-draft", "feedback-body")]
sys.exit(0 if all(p.is_file() and p.stat().st_size for p in paths) else 1)
'
uv run python -c 'import json, pathlib, sys, time
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
'
uv run python -c 'import pathlib; print(*sorted(pathlib.Path("narrative-traces/structural").rglob("*.nt")), sep="\n")'
uv run python -c 'import pathlib; print(*sorted(pathlib.Path("narrative-traces/traces").rglob("*.md")), sep="\n")'
uv run python -c 'import pathlib; print(*sorted(pathlib.Path("test-narratives").rglob("*.received.nt")), sep="\n")'
uv run python -c 'import sys; from narrativetrace.config import ConfigResolver; value = (ConfigResolver().resolve("approval", "") or "").strip().lower(); sys.exit(0 if value in {"1", "true", "yes", "on"} else 1)'
uv run python -c 'import pathlib; print(*sorted(pathlib.Path("narrative-traces/diagrams").rglob("*.mmd")), sep="\n")'
```

- `git`, to read which files are in your project:

```
git ls-files '*.py' 'pyproject.toml'
git ls-files '*.py' 'pyproject.toml' | uv run python -c 'import sys
sys.exit(0 if sys.stdin.read().split() else 1)
'
```

Two skills also edit your project's files. The install skill adds the NarrativeTrace packages to your `pyproject.toml` and shows a first trace in a small script; the Clarity skill adds its package as a development dependency, renames the identifiers its report flags in your source files, and re-runs your tests after the renames.

## What the skills fetch

- The skills pin no NarrativeTrace version and look nothing up themselves: they install without a version, so `uv` resolves the newest release from PyPI, as it resolves any dependency. The packages they add are `narrativetrace`, `narrativetrace-clarity`.
- `uv run` first brings your project's environment up to date from the same index, as it does whenever you run it.
- Your own `uv` then resolves what those packages depend on. The skills fetch nothing else.

## What the skills send

Nothing leaves your machine from this plugin: no skill uploads, posts or transmits anything, and it has no hooks, MCP servers or network code of its own.

`narrativetrace-feedback` is the one skill about reporting a defect in NarrativeTrace itself. It drafts a report from your project into `build/narrativetrace/feedback/feedback-draft.md` and `build/narrativetrace/feedback/feedback-body.md` (the install coordinates, the doctor's JSON report and at most one structural trace, and it refuses to write a report that carries a value from your own run), shows you the whole draft, and asks once whether to file it. Only after your yes does it print a pre-filled issue address (https://github.com/narrativetrace/narrativetrace-python/issues/new?...) and the name of the body file to paste. The command line it runs opens no browser and makes no request of its own. The skill never opens that address, never runs the command it prints, and never runs `gh`: nothing is sent unless you open the address yourself, in your own browser, under your own account, and the issue you file is public.

## License and links

The skills in this plugin are licensed under Apache-2.0.

- Homepage: https://narrativetrace.ai
- Repository: https://github.com/narrativetrace/narrativetrace-python

NarrativeTrace is provided as is: no warranty, and no guarantee that it fits your purpose. Use it at your own risk.

The Apache-2.0 text, [LICENSE-APACHE](https://github.com/narrativetrace/narrativetrace-python/blob/main/LICENSE-APACHE), section 7:

> 7. Disclaimer of Warranty. Unless required by applicable law or
> agreed to in writing, Licensor provides the Work (and each
> Contributor provides its Contributions) on an "AS IS" BASIS,
> WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
> implied, including, without limitation, any warranties or conditions
> of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
> PARTICULAR PURPOSE. You are solely responsible for determining the
> appropriateness of using or redistributing the Work and assume any
> risks associated with Your exercise of permissions under this License.

Section 8, "Limitation of Liability", of the same file limits liability further (Apache-licensed parts only).

The NarrativeTrace runtime that these skills install is licensed under the Business Source License 1.1; see [LICENSE](https://github.com/narrativetrace/narrativetrace-python/blob/main/LICENSE).
