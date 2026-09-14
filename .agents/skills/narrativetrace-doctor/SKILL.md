---
name: narrativetrace-doctor
description: "Diagnoses a NarrativeTrace Python install and configuration. Use when nothing is being traced, no trace output files appear, DuplicateConfigurationError shows up on startup, a *args method's parameters render as one args: [...] value, or you are not sure NarrativeTrace is wired up correctly. Checks the interpreter and pytest versions, that all eight narrativetrace-* packages agree on one version, NARRATIVETRACE_OUTPUT, that the pytest plugin is registered and not disabled, unrecognized narrativetrace.toml keys, an imported-but-unused not_traced_field/__nt_not_traced__ marker, whether redaction is proven in a test, and stale approval-trace diffs. Read-only -- makes no changes. Say 'check my narrativetrace setup', 'is narrativetrace broken', or 'why isn't anything being traced' to invoke it."
---

# narrativetrace-doctor

## 1. Run the doctor and read its report

```bash
uv run narrativetrace doctor || true
```

**verify:** `uv run narrativetrace doctor --json | uv run python -c 'import json, sys
report = json.load(sys.stdin)
findings = report.get("findings")
sys.exit(1 if not isinstance(findings, list) or len(findings) != 11 else 0)
'`

**failure:** the CLI's JSON output does not parse, or is missing findings — the CLI crashed instead of reporting a finding. Fix: re-run `uv run narrativetrace doctor --json` directly and read the raw output -- a crash here is a doctor bug, never a project finding

## 2. Prove redaction in a test

```bash
uv run python -c 'print(
    "Render a call with a deny-listed parameter name (e.g. password or token) in a test and "
    "assert the output contains [REDACTED], and that a neighboring non-sensitive value is still "
    "present."
)
'
```

**verify:** `uv run narrativetrace doctor --json | uv run python -c 'import json, sys
report = json.load(sys.stdin)
by_id = {f["id"]: f for f in report["findings"]}
finding = by_id.get("trap.redaction-proof")
sys.exit(1 if finding is None or finding["status"] not in ("pass", "fail") else 0)
'`

**failure:** not_traced_field/__nt_not_traced__ is present but never applied — trusting redaction by inspection instead of proving it in a test. Fix: render a call with a deny-listed parameter name and assert the output contains "[REDACTED]"

## 3. Read the rendered trace before asserting

```bash
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
```

## 4. Approval flow: diff the structural trace, not just values

**Flagged:** unstudied -- eval cell pending

```bash
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
```

## Always

- Run the doctor CLI and read its report before making any change. (the tested tooling already computed the finding -- re-deriving it by hand risks disagreeing with what ships)

## Never

- Never have this skill edit, generate, or delete a file. (narrativetrace-doctor is scoped read-only by design -- generation of the redaction-proof test itself is a separate, later skill)
- Never claim a finding passed without having run the doctor CLI in this session. (self-reported success overstates reality -- a build claimed green that does not reproduce from clean is not evidence; verify is never 'ask the agent')
