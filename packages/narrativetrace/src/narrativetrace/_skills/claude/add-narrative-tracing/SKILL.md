---
name: add-narrative-tracing
description: "Installs NarrativeTrace into a Python project and gets it to a first trace. Use when NarrativeTrace is not yet installed, a project needs its very first traced call, or traces need to reach a real logger instead of bare print statements. Installs narrativetrace with uv add, wraps an object with trace_object, renders and runs the first trace, then wires the stdlib logging bridge so traces reach your logger. Applies the doctor's framework-wiring fixes for the frameworks the project already uses, and runs narrativetrace doctor to confirm the install is correctly wired -- narrativetrace-doctor owns diagnosis from there -- and previews the agent-skills install so the next session finds them. Say 'add narrative tracing to my service', 'install narrativetrace', 'get a trace in 60 seconds', 'wrap this object so I can see a trace', or 'send my traces to my logger' to invoke it."
when_to_use: "A project does not have NarrativeTrace yet, or has the package installed but has never produced a trace, or traces print to the console but nothing forwards them to a real logger."
allowed-tools: Bash(uv *), Bash(git *)
---

# add-narrative-tracing

## 1. Install with the real toolchain

```bash
uv sync --all-packages
```

**verify:** `uv run narrativetrace doctor --json | uv run python -c 'import json, sys
report = json.load(sys.stdin)
bad = [f for f in report["findings"] if f["id"].startswith("toolchain.") and f["status"] != "pass"]
if bad:
    print(json.dumps(bad))
sys.exit(1 if bad else 0)
'`

**failure:** a sibling narrativetrace-* package disagrees on version — an installed distribution outside the lockstep version the other narrativetrace-* packages share. Fix: run the narrativetrace-doctor skill's toolchain.package-versions check, then pin every narrativetrace-* dependency to the same version and `uv sync`

## 2. Wire the frameworks this project already uses

```bash
uv run narrativetrace doctor || true
```

**verify:** `uv run narrativetrace doctor --json | uv run python -c 'import json, sys
from narrativetrace_tooling.frameworks.table import wiring_check_ids
report = json.load(sys.stdin)
ids = set(wiring_check_ids())
bad = [f for f in report["findings"] if f["id"] in ids and f["status"] != "pass"]
for f in bad:
    print(f["id"] + ": " + f["fix"])
sys.exit(1 if bad else 0)
'`

**failure:** a config.<framework>-* finding fails — the doctor detected a framework this project uses whose NarrativeTrace integration is not added, or is added but never wired. Fix: run the doctor; apply every config.<framework>-* fix it prints, in order; a framework it reports as having no integration shipped is left alone

## 3. First trace: wrap, call, render, run

**when:** if the project already has an application entry point — a script or module that starts it, a web or application framework the doctor reports — do not create a demo main.py: run the application the way it already runs, exercise one real boundary, and read that request's trace; the verify below is for the standalone script, and in an existing application the step is done when that request's trace is in the output; otherwise create the smallest script as follows

<!-- snippet: examples/sixty_seconds/main.py -->
```python
# main.py
from narrativetrace import ContextVarNarrativeContext, IndentedTextRenderer, TraceId, trace_object


class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


# snippet:begin fixedTraceId
# A fixed trace id, adopted so this page's embedded output always names the same trace. A real
# run generates a random one every time (never this -- it is this DEMO's own constant, not the
# library default) via the same TraceId.adopt_trace_id a servlet-style boundary uses for an
# inbound trace header.
DEMO_TRACE_ID = TraceId("a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4")

# snippet:end fixedTraceId

context = ContextVarNarrativeContext()
context.adopt_trace_id(DEMO_TRACE_ID)
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

print(IndentedTextRenderer().render(context.capture_trace()))
```
<!-- /snippet -->

**verify:** `uv run python main.py`

**failure:** a *args method's parameters render as one args: [...] value — inspect.signature has nothing named to reconstruct per-argument that Python itself does not have. Fix: supply explicit names: @traced("first", "second", ...) above the method

## 4. Send it to your logger

**when:** if the project already has an application entry point — a script or module that starts it, a web or application framework the doctor reports — do not create a second main.py or a second logging setup: add the filter and the export_to_logger call to the application's own logging configuration and the boundary you exercised; the verify below is for the standalone script, and in an existing application the step is done when that boundary's trace reaches the application's own logger; otherwise create the smallest script as follows

<!-- snippet: examples/sixty_seconds/main_with_logger.py -->
```python
# main.py
import logging  # new: stdlib logging -- the sink this step sends the trace to
import sys  # new: stdout target for the handler below

from narrativetrace import (
    ContextVarNarrativeContext,
    IndentedTextRenderer,
    NarrativeContextFilter,  # new: injects traceName/runName onto every log record
    TraceId,
    export_to_logger,  # new: replays an already-captured trace through your logger, one call
    trace_object,
)


class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


# snippet:begin fixedTraceId
# A fixed trace id, adopted so this page's embedded output always names the same trace. A real
# run generates a random one every time (never this -- it is this DEMO's own constant, not the
# library default) via the same TraceId.adopt_trace_id a servlet-style boundary uses for an
# inbound trace header.
DEMO_TRACE_ID = TraceId("a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4")

# snippet:end fixedTraceId

# new: a plain stdlib logging setup -- the shape a real app's own logging config already has
handler = logging.StreamHandler(sys.stdout)
handler.addFilter(NarrativeContextFilter())  # new: makes traceName/runName available below
# new: DEBUG so export_to_logger's records pass the handler; the format reads the filter's keys
logging.basicConfig(
    level=logging.DEBUG, format="[%(traceName)s] [%(runName)s] %(message)s", handlers=[handler]
)

context = ContextVarNarrativeContext()
context.adopt_trace_id(DEMO_TRACE_ID)
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

trace = context.capture_trace()  # new: capture once, reuse for both the print and the export
print(IndentedTextRenderer().render(trace))

export_to_logger(trace)  # new: sends the same captured trace through the configured logger
```
<!-- /snippet -->

**verify:** `uv run python main_with_logger.py`

## 5. Run the doctor and resolve its findings

```bash
uv run narrativetrace doctor || true
```

**verify:** `uv run narrativetrace doctor --json | uv run python -c 'import json, sys
report = json.load(sys.stdin)
findings = report.get("findings")
sys.exit(1 if not isinstance(findings, list) or len(findings) != 19 else 0)
'`

## 6. Install the skills for next time

```bash
uv run narrativetrace init --dry-run
```

**done when:** the preview wrote nothing; the next session verifies with narrativetrace-verify — once a change's tests are green, it reads the trace before it reports

**verify:** `uv run python -c 'import pathlib, subprocess, sys
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
'`

**failure:** the command exits 1 with no carrier resolved — no narrativetrace-skills distribution is installed and this project's own narrativetrace bundles no reachable fallback. Fix: run `uv add narrativetrace-skills`, or point --from at a local carrier directory or wheel

## Always

- Reinstall clean (`uv sync`) rather than trusting whatever is already in the virtual environment. (a mismatched sibling version or a stale lockfile is the single most common install failure, and it only surfaces on a clean install)

## Never

- Never assume a step worked without running its verify. (self-reported success overstates reality -- a build claimed green that does not reproduce from clean is not evidence)
- Never skip the final narrativetrace doctor call. (it is the seam that catches anything these five steps did not -- narrativetrace-doctor owns diagnosis from here)
- Never apply the installer without showing its diff first. (it writes into AGENTS.md and the project's skill directories, and the approval for that is a person reading the diff -- run it with --dry-run, show the output, and let them run it again without the flag)
