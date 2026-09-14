---
name: add-narrative-tracing
description: "Installs NarrativeTrace into a Python project and gets it to a first trace. Use when NarrativeTrace is not yet installed, a project needs its very first traced call, or traces need to reach a real logger instead of bare print statements. Installs narrativetrace with uv add, wraps an object with trace_object, renders and runs the first trace, then wires the stdlib logging bridge so traces reach your logger. Ends by running narrativetrace doctor to confirm the install is correctly wired -- narrativetrace-doctor owns diagnosis from there. Say 'add narrative tracing to my service', 'install narrativetrace', 'get a trace in 60 seconds', 'wrap this object so I can see a trace', or 'send my traces to my logger' to invoke it."
when_to_use: "A project does not have NarrativeTrace yet, or has the package installed but has never produced a trace, or traces print to the console but nothing forwards them to a real logger."
allowed-tools: uv, git
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

## 2. First trace: wrap, call, render, run

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

## 3. Send it to your logger

<!-- snippet: examples/sixty_seconds/main_with_logger.py -->
```python
# main.py
import logging
import sys

from narrativetrace import (
    ContextVarNarrativeContext,
    IndentedTextRenderer,
    NarrativeContextFilter,
    TraceId,
    export_to_logger,
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

handler = logging.StreamHandler(sys.stdout)
handler.addFilter(NarrativeContextFilter())
logging.basicConfig(
    level=logging.DEBUG, format="[%(traceName)s] [%(runName)s] %(message)s", handlers=[handler]
)

context = ContextVarNarrativeContext()
context.adopt_trace_id(DEMO_TRACE_ID)
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

trace = context.capture_trace()
print(IndentedTextRenderer().render(trace))

export_to_logger(trace)
```
<!-- /snippet -->

**verify:** `uv run python main_with_logger.py`

## 4. Run the doctor and resolve its findings

```bash
uv run narrativetrace doctor || true
```

**verify:** `uv run narrativetrace doctor --json | uv run python -c 'import json, sys
report = json.load(sys.stdin)
findings = report.get("findings")
sys.exit(1 if not isinstance(findings, list) or len(findings) != 11 else 0)
'`

## Always

- Reinstall clean (`uv sync`) rather than trusting whatever is already in the virtual environment. (a mismatched sibling version or a stale lockfile is the single most common install failure, and it only surfaces on a clean install)

## Never

- Never assume a step worked without running its verify. (self-reported success overstates reality -- a build claimed green that does not reproduce from clean is not evidence)
- Never skip the final narrativetrace doctor call. (it is the seam that catches anything these four steps did not -- narrativetrace-doctor owns diagnosis from here)
