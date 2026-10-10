---
name: narrativetrace-verify
description: "Verifies a change in a Python project by reading what the code actually did before saying it is done. Use after the tests are green and before reporting a change that crosses collaborators, branches, retries, runs async, carries state between calls, or touches code not written in this session -- and skip it, saying why, for a pure function or a one-class edit. Writes the intent down first, runs the smallest real path with NarrativeTrace on, reads the value-free structural trace against the intent, opens values only on the span that looks wrong, fixes and re-reads, then pins the flow as an approval baseline behind your yes and reports what the trace showed, citing span ids. Say 'verify this change with the trace', 'check what the code actually did', 'did the flow do what I meant', or 'pin this flow as a baseline' to invoke it."
when_to_use: "Non-obvious triggers: the suite is green but the change touched more call sites than it added; a notification, payment or retry path changed; a .received.nt appeared after a test run; you are about to write 'tests pass' as the whole report."
---

# narrativetrace-verify

## 1. Decide whether to trace, and say so

**done when:** before anything runs, the reply says which it is: 'tracing: <the reason>' when the change crosses two or more collaborators over a boundary, branches, retries, runs async or concurrently, carries state between calls, touched more call sites than it added, or includes code not written in this session; or 'skipping narrativetrace-verify: <a pure function | a one-class edit with no collaborator | a flow one test already walks end to end>' — a skip ends the skill here, and that sentence is the report. A whole flow's .nt is dozens of lines: cheap where the path is not obvious, waste where it is

## 2. Write the intent down before running anything

**done when:** three to six lines in the reply, under the word Intent, written before the first traced run: which collaborators the change touches, in which order, under which branch, how many times — the oracle the trace is read against, never edited after the run

## 3. Run the smallest real path with tracing on

**when:** the project already has a test that drives the changed path through its real collaborators, each wrapped with the narrative_trace fixture: run that one — again, if it already ran: a trace from a run made before the Intent was written does not count; otherwise write the smallest one, as below

<!-- snippet: examples/sixty_seconds/test_place_order_flow.py -->
```python
"""The smallest test that drives a real path through its collaborators, traced: the
``narrative_trace`` fixture is the capture, and every collaborator on the path is wrapped with it.
After a run, ``narrative-traces/structural/<module>/<test>.nt`` holds the flow's shape and
``narrative-traces/traces/<module>/<test>.md`` its values."""

from narrativetrace import ContextVarNarrativeContext, trace_object


class Inventory:
    def reserve(self, product_id: str, quantity: int) -> str:
        return f"R-{product_id}-{quantity}"


class OrderService:
    def __init__(self, inventory: Inventory) -> None:
        self._inventory = inventory

    def place_order(self, customer_id: str, product_id: str, quantity: int) -> str:
        reservation = self._inventory.reserve(product_id, quantity)
        return f"ORD-{customer_id}-{reservation}"


def test_customer_places_an_order(narrative_trace: ContextVarNarrativeContext) -> None:
    inventory = trace_object(Inventory(), narrative_trace)
    service = trace_object(OrderService(inventory), narrative_trace)

    assert service.place_order("cust-1", "prod-42", 3) == "ORD-cust-1-R-prod-42-3"
```
<!-- /snippet -->

**done when:** the test passed and its .nt was written under narrative-traces/structural/ by this run, after the Intent

**verify:** `uv run pytest <the smallest test that drives the real path>`

**failure:** no .nt for the test appears under narrative-traces/structural — the test does not request the narrative_trace fixture, the collaborators on the path are not wrapped with it, or the pytest plugin is not registered. Fix: run narrativetrace-doctor and apply its fix, then run the test again

## 4. Read the structural trace first, against the intent

```bash
uv run python -c 'import pathlib; print(*sorted(pathlib.Path("narrative-traces/structural").rglob("*.nt")), sep="\n")'
```

**done when:** the .nt of the test just run was opened and read whole before any value was looked at, and the reply walks it against the intent — calls, order, branch, multiplicity — naming every match and every mismatch by its span id (#2.1); the shapes below are the checklist

## 5. Open values on the span that looks wrong, and only there

**when:** only when the structural read named a span that does not match the intent; otherwise go on to the pin

```bash
uv run python -c 'import pathlib; print(*sorted(pathlib.Path("narrative-traces/traces").rglob("*.md")), sep="\n")'
```

**done when:** only the flagged span was read in the .md narrative, found by the id the .nt gave it — not the whole file; a [REDACTED] value stays redacted

## 6. Fix, re-run, read again

**when:** only when the structural read named a span that does not match the intent; otherwise go on to the pin

```bash
uv run pytest <the smallest test that drives the real path>
```

**done when:** the same test ran again after the fix and its new .nt was read whole: the span that was wrong now matches the intent, and a fix that changed the shape was read again from the structural read

## 7. Turn approval mode on

**when:** if approval mode is off — nothing sets NARRATIVETRACE_APPROVAL or `approval = true`, or the doctor's config.approval-mode finding fails; when it is already on, go straight to the run

**done when:** `pyproject.toml` carries `approval = true` under `[tool.narrativetrace]`, and `.gitignore` carries the line `*.received.nt` so a review copy is never committed

**verify:** `uv run python -c 'import sys; from narrativetrace.config import ConfigResolver; value = (ConfigResolver().resolve("approval", "") or "").strip().lower(); sys.exit(0 if value in {"1", "true", "yes", "on"} else 1)'`

**failure:** the verify still exits 1 after the edit — the key sits under another table, the project also has a narrativetrace.toml (two configuration sources stop every run with DuplicateConfigurationError), or NARRATIVETRACE_APPROVAL=false is set in the environment, which wins over both. Fix: keep one source — `approval = true` directly under `[tool.narrativetrace]`, or at the top of narrativetrace.toml — unset the variable, and run the verify again

## 8. Run the suite in approval mode and show every .received.nt

```bash
uv run pytest || true
uv run python -c 'import pathlib; print(*sorted(pathlib.Path("test-narratives").rglob("*.received.nt")), sep="\n")'
```

**done when:** approval mode compares every traced test, not only the one this skill ran, so the run that writes the review copies is the whole suite; the first run of a test with no baseline fails on purpose — that failure is what writes its review copy — and the whole text of each .received.nt that run wrote is in the reply, not a summary of it — it holds names and shape and no value, which is why it is safe to commit once approved; where a .approved.nt already existed, the reply also names what the delta changed, by span id, in the program's own words, and whether it was meant

## 9. Ask once whether to pin it, then stop the turn

**done when:** the answer is the user's next message, never something assumed in this one. Do not run narrativetrace-approve before the user says yes — promoting is the pinning. Everything else — the report, every caveat, and what promoting does — goes before the question; the question is ONE sentence ending in a question mark and it is the reply's last line, so a reply whose last line is a sentence after the question has not asked it.

## 10. Promote what was shown, and nothing else

```bash
uv run narrativetrace-approve
```

**done when:** each .approved.nt now holds exactly the text that was shown and no .received.nt is left beside it — `git status --short test-narratives` lists the new or changed .approved.nt files and nothing else; those are what get committed — and the whole suite passes again after the promotion

**verify:** `uv run pytest`

## 11. Report what the trace showed

**done when:** two sentences on what the trace showed, every claim citing the span id it rests on — a claim without an id is not a claim, and only ids in the .nt that was read count — with the .nt attached or quoted; 'tests pass' alone is not the report

## Which flavour answers which question

| flavour | where | carries | answers |
|---|---|---|---|
| structural `.nt` | `narrative-traces/structural/<test module>/<test>.nt` | shape only: calls, order, nesting, parameter names, multiplicity, span ids — dozens of lines for a whole flow | did the flow do what I meant? |
| Markdown narrative | `narrative-traces/traces/<test module>/<test>.md` | values (redacted), outcomes, durations | what value crossed this boundary? — read one span, by id |
| indented text | `IndentedTextRenderer`, the failing test's output | the same values as plain text | the same question, in a console or a failure message |
| sequence diagram | `narrative-traces/diagrams/<test module>/<test>.mmd` | who called whom, in order, across threads and tasks | ordering across components, threads and tasks |
| approval delta | the failing test's message: `.received.nt` against `.approved.nt` under `test-narratives/` | what changed in the shape, citing both sides' ids | is this change intended? |
| prose | `ProseRenderer` | narration for a person | explaining the flow to the user — never read it to check the code |

Use the cheapest flavour that answers the question, and look at values only where the shape says
to look. A span id (`#1`, `#1.3`, `#1.3.2`) is the span's position in the tree and the same in
every flavour: find in the `.md` the span the `.nt` flagged, by its id. Redaction stays on — the
deny-list and `[REDACTED]` are never turned off to see more; a redacted value that matters is
reasoned about by its parameter name and the shape around it.

## Shapes that mean something went wrong

- a call made twice that the intent makes once
- a call before its precondition — a notification before the payment that it announces
- a branch never taken that the intent takes
- a retry that masks a failure
- a side effect inside a loop
- a swallowed exception: a thrown outcome `!!` under a call that returned normally
- a cleanup that never ran
- a value crossing a boundary that should have been redacted

## Always

- Cite a span id for every claim about the trace. (an id points at one span in every flavour, so a reviewer can check the claim; a claim without one cannot be checked)
- Use the cheapest flavour that answers the question. (the structural trace first and a value on one span only is what keeps the common case near zero tokens)
- Show the whole .received.nt before asking anything. (the baseline becomes the contract every later change is held to, and a person can only approve what they have actually read)
- End the turn on the question, with nothing after it. (the answer is the user's next message, never something assumed in this one. Do not run narrativetrace-approve before the user says yes — promoting is the pinning.)

## Never

- Never report a change as done on green tests alone once this skill decided to trace. (the suite checks what someone thought to assert; the trace shows what the code did)
- Never read a trace against nothing. (an intent written after the run bends to whatever happened — that is why it comes first)
- Never turn redaction off to see more. (a redacted value that matters is reasoned about by its name and shape; turning redaction off puts the user's secrets in the transcript)
- Never promote a baseline in the turn that asked. (approval is the user's next message -- a yes assumed in the same turn is not one)
- Never edit the .received.nt after showing it. (what was approved has to be what is promoted, so a changed run is rendered again and shown again)
- Never commit a .received.nt. (it is the review copy; the committed contract is the .approved.nt)
