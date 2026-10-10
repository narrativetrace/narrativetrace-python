---
name: narrativetrace-debug
description: "Finds the cause of a wrong result in a Python project by reading what the code did with the values, not by stepping through it. Use when a symptom is reported -- a wrong amount, a wrong id, a call in the wrong order, a test that fails with a value nobody expected. Reproduces it with the smallest input and NarrativeTrace on, finds the first span where a value diverges and names it by its span id (the sequence diagram first when threads or tasks are involved), narrows to that span's sub-tree, fixes it there and checks the structural trace shows nothing else moved, pins the reproduction as a regression test and an approval baseline behind your yes, and reports the root cause by span id. Hands a defect in NarrativeTrace itself to narrativetrace-feedback. Say 'debug this with the trace', 'find where this value goes wrong', or 'why is this result wrong' to invoke it."
---

# narrativetrace-debug

## 1. Reproduce the symptom with tracing on

**when:** a test already drives the path with the input from the symptom, run that one; otherwise write the smallest one, as below — the reported input, through the real collaborators each wrapped with trace_object and the narrative_trace fixture, asserting the value the symptom says should have come out

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

**done when:** the test ran with the reported input, and its .md narrative was written by this run

**verify:** `uv run pytest <the test that reproduces the symptom>`

**failure:** no .md for the test appears under narrative-traces/traces — the test does not request the narrative_trace fixture, the collaborators on the path are not wrapped with it, or the pytest plugin is not registered. Fix: run narrativetrace-doctor and apply its fix, then run the test again

## 2. Find the symptom in the values

```bash
uv run python -c 'import pathlib; print(*sorted(pathlib.Path("narrative-traces/traces").rglob("*.md")), sep="\n")'
```

**done when:** the reported value is in this run's .md narrative, or the reproducing test fails on it — a symptom that does not reproduce is said so, and the loop stops here

## 3. Across threads, read the sequence diagram first

**when:** only when the path crosses threads or tasks — the .nt shows a fork, async or fire-and-forget marker — or the symptom is about order (a call that ran before or after another); otherwise go straight to localizing

```bash
uv run python -c 'import pathlib; print(*sorted(pathlib.Path("narrative-traces/diagrams").rglob("*.mmd")), sep="\n")'
```

**done when:** the reproduction's .mmd was read before any span's values, and the reply says which call ran before which across the threads, by the span id in each call's note — the span it points to is the one localized next

## 4. Localize by reading: name the first span where a value diverges

**done when:** the reproduction's .md spans were read from the root down until the first one whose inputs are what the symptom implies but whose result, the value it passes on, or the branch it takes is not; the reply names that span by its id (#1.3) and the boundary — the collaborator, the parameter or return, the value that arrived and the value that left — before any code is changed: by reading, not by stepping through a debugger or adding prints

## 5. Bisect by span, not by file

**when:** only when the value went into the diverging span right and came out wrong, and what happens in between is more than that span's own few lines; otherwise the diverging span is the defect — go on to the fix

```bash
uv run pytest <the test that reproduces the symptom>
```

**done when:** only the sub-tree under the diverging id was read on each re-run — the spans whose id begins with it (#1.3, #1.3.1, #1.3.2) — and where the work inside that span is not traced, the collaborator it calls was wrapped with trace_object in the reproducing test, as the listing above wraps its inventory, and the run repeated, until the divergence sits in the smallest span that has it; never not_traced_field, __nt_not_traced__ or @not_traced to narrow — in Python they redact a value, they do not scope a trace

## 6. Hand a defect in NarrativeTrace itself to narrativetrace-feedback

**when:** only when the trace and the code disagree — a call the code makes has no span, a span shows a value the code did not pass, one span has two ids in two flavours — or the diverging span is inside NarrativeTrace; otherwise go on to the fix

**done when:** narrativetrace-feedback was started with the span id and the value-free .nt — never a value from the trace — and the project's code was not changed to work around it; the loop ends with that hand-off

## 7. Fix it in the diverging span, re-run the same input, read the same span

```bash
uv run pytest <the test that reproduces the symptom>
```

**done when:** the change is in the code of that span — the method the diverging id names, or what it calls — and the reproducing test passes; the same span, by the same id, now carries the value the symptom implied; a change anywhere else that makes the test pass silences the symptom and leaves the defect, so it is undone

**verify:** `uv run pytest <the test that reproduces the symptom>`

## 8. Check that nothing else moved

```bash
uv run python -c 'import pathlib; print(*sorted(pathlib.Path("narrative-traces/structural").rglob("*.nt")), sep="\n")'
```

**done when:** the fixed run's .nt was read whole and compared, line by line, with the call lines of the reproduction's .md — a red run writes no .nt (the .nt on disk is the last green one), so the shape before the fix is the .md's calls and ids without their values: the same calls in the same order under the same ids; a value fix moves no line of a value-free trace, and every line that did move is named by its id in the reply and either explained by the fix or undone

## 9. Keep the reproduction as the regression test

**done when:** the reproducing test stays in the suite with the input from the symptom and asserts the value the fixed span now carries — not only that nothing raises — so it fails when the fix is undone; its structural trace is what the pin below makes the baseline

## 10. Turn approval mode on

**when:** if approval mode is off — nothing sets NARRATIVETRACE_APPROVAL or `approval = true`, or the doctor's config.approval-mode finding fails; when it is already on, go straight to the run

**done when:** `pyproject.toml` carries `approval = true` under `[tool.narrativetrace]`, and `.gitignore` carries the line `*.received.nt` so a review copy is never committed

**verify:** `uv run python -c 'import sys; from narrativetrace.config import ConfigResolver; value = (ConfigResolver().resolve("approval", "") or "").strip().lower(); sys.exit(0 if value in {"1", "true", "yes", "on"} else 1)'`

**failure:** the verify still exits 1 after the edit — the key sits under another table, the project also has a narrativetrace.toml (two configuration sources stop every run with DuplicateConfigurationError), or NARRATIVETRACE_APPROVAL=false is set in the environment, which wins over both. Fix: keep one source — `approval = true` directly under `[tool.narrativetrace]`, or at the top of narrativetrace.toml — unset the variable, and run the verify again

## 11. Run the suite in approval mode and show every .received.nt

```bash
uv run pytest || true
uv run python -c 'import pathlib; print(*sorted(pathlib.Path("test-narratives").rglob("*.received.nt")), sep="\n")'
```

**done when:** approval mode compares every traced test, not only the one this skill ran, so the run that writes the review copies is the whole suite; the first run of a test with no baseline fails on purpose — that failure is what writes its review copy — and the whole text of each .received.nt that run wrote is in the reply, not a summary of it — it holds names and shape and no value, which is why it is safe to commit once approved; where a .approved.nt already existed, the reply also names what the delta changed, by span id, in the program's own words, and whether it was meant

## 12. Ask once whether to pin it, then stop the turn

**done when:** the answer is the user's next message, never something assumed in this one. Do not run narrativetrace-approve before the user says yes — promoting is the pinning. Everything else — the report, every caveat, and what promoting does — goes before the question; the question is ONE sentence ending in a question mark and it is the reply's last line, so a reply whose last line is a sentence after the question has not asked it.

## 13. Promote what was shown, and nothing else

```bash
uv run narrativetrace-approve
```

**done when:** each .approved.nt now holds exactly the text that was shown and no .received.nt is left beside it — `git status --short test-narratives` lists the new or changed .approved.nt files and nothing else; those are what get committed — and the whole suite passes again after the promotion

**verify:** `uv run pytest`

## 14. Report the root cause as the trace showed it

**done when:** the root cause in the user's own terms — the span id where it diverged, the value that arrived and the value that left, the branch it took — and what the fix changed in that span; every claim cites the span id it rests on, from the .nt or .md read in this session: a claim without an id is not a claim. The report is written in full before the pin question, where the gate puts it, and the closing reply after the promotion names the span id again in its one-line summary of the cause

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
- Narrow to one span before reading its values. (debugging is where values pay for themselves, but only on the span that diverged — a whole trace of values buries the one that matters)
- Show the whole .received.nt before asking anything. (the baseline becomes the contract every later change is held to, and a person can only approve what they have actually read)
- End the turn on the question, with nothing after it. (the answer is the user's next message, never something assumed in this one. Do not run narrativetrace-approve before the user says yes — promoting is the pinning.)

## Never

- Never change code before the diverging span is named. (a fix made before the trace says where the value went wrong is a guess, and a guess that turns the test green hides the defect it missed)
- Never make the symptom go away somewhere other than the diverging span. (a correction downstream, a caught exception or a changed expectation silences the symptom and leaves the defect for the next caller of that span)
- Never turn redaction off to see more. (a redacted value that matters is reasoned about by its name and shape; turning redaction off puts the user's secrets in the transcript)
- Never promote a baseline in the turn that asked. (approval is the user's next message -- a yes assumed in the same turn is not one)
- Never edit the .received.nt after showing it. (what was approved has to be what is promoted, so a changed run is rendered again and shown again)
- Never commit a .received.nt. (it is the review copy; the committed contract is the .approved.nt)
