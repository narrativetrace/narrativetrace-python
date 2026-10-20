---
name: narrativetrace-explain
description: "Use when someone asks what an application or a flow actually does, with nothing broken and no change needing verification: 'show me what my application actually does', 'walk me through what happens when a user checks out', 'I inherited this service, how does an order flow', 'what does this endpoint call'. Load it BEFORE reading source files to describe them: it explains a Python application by running one scenario with NarrativeTrace on and reading the trace of what happened \u2014 evidence of the run, not a reading of the code. Decides first whether a trace is worth it: a question ten lines of source answer is answered from the source, with no install and no run. Otherwise it runs one existing test or entry point for that flow \u2014 installing through add-narrative-tracing when the project has none \u2014 reads the value-free structural trace, and explains the run by span id, marking what it inferred and naming the code no span covered. Hands a defect to narrativetrace-debug, a change to narrativetrace-verify."
---

# narrativetrace-explain

## 1. Decide whether the source already answers it, and say so

**done when:** before anything is installed or run, the reply says which it is: 'reading the source: <the reason>' when the question is about a pure function, one class with no collaborator, or a path ten lines of source settle — the answer is then that reading, with no install and no run, and the skill ends there; or 'tracing: <the reason>' when the flow crosses two or more collaborators over a boundary, branches, retries, runs async or concurrently, carries state between calls, or is code nobody in this session wrote. A whole flow's .nt is dozens of lines: cheap where the path is not obvious, waste where the source is already the answer

## 2. Choose the one scenario that already exercises the flow

**done when:** the reply names ONE scenario — an existing test, or the entry point a reader would run — and which call of the flow asked about it drives; a scenario is written only where the project has none, and the reply says which of the two it is. Two scenarios is two traces to read where one answers the question

## 3. Install tracing first when the project has none

**when:** only when the project has no NarrativeTrace at all — no dependency on it in pyproject.toml and nothing under narrative-traces; where it is already installed, go straight to the run

**done when:** add-narrative-tracing was followed to its own first trace and this skill resumed at the run below; nothing beyond that install was changed — an explanation does not refactor the code it is about

## 4. Run that one scenario with tracing on

**when:** the project already has a test or entry point that exercises the flow — run that one, as it is; where none exists, add-narrative-tracing's own first-trace step is how one gets written, and it comes back here

```bash
uv run pytest <the test that exercises the flow you were asked about>
```

**done when:** the scenario ran and wrote a trace of its own: narrative-traces/structural holds an .nt for it, and narrative-traces/traces the .md beside it — a run that writes nothing is the failure below, never an answer; and the scenario ran as it was found, because a scenario edited to make the flow clearer is no longer the flow

**failure:** the scenario runs but nothing appears under narrative-traces — the test does not request the narrative_trace fixture, the collaborators on the flow are not wrapped with it, or the pytest plugin is not registered, so there is nothing to read. Fix: run narrativetrace-doctor and apply its fix, then run the scenario again

## 5. Read the structural trace first, in the order it ran

```bash
uv run python -c 'import pathlib; print(*sorted(pathlib.Path("narrative-traces/structural").rglob("*.nt")), sep="\n")'
```

**done when:** the .nt the scenario just wrote was opened and read whole before any value was looked at, and the reply walks it in its own order by span id (#1, #1.1, #1.2): which call ran under which, how many times, and which branch the run took — the flavours below say which file answers which question

## 6. Open values only where the question needs one

**when:** only when the question is about a value that crossed a boundary, or about where the time went — the .nt carries neither; otherwise the shape is the whole answer

```bash
uv run python -c 'import pathlib; print(*sorted(pathlib.Path("narrative-traces/traces").rglob("*.md")), sep="\n")'
```

**done when:** only the spans the question needs were read in the .md narrative, found by the id the .nt gave them — not the whole file; a [REDACTED] value stays redacted and is reasoned about by its parameter name and the shape around it

## 7. Hand off when it stops being an explanation

**when:** only when the run shows something wrong — one of the shapes below, or a value that is not what the flow implies — or a change of this session's own is what the user is really asking about; otherwise go on to the explanation

**done when:** narrativetrace-debug was started, with the span id of the first call that looks wrong, when the run showed a defect; or narrativetrace-verify when what needs reading is a change this session made. The explanation written so far goes with the hand-off, and this skill fixes nothing itself

## 8. Explain the run by span id, and mark what you inferred

**done when:** the explanation is in the user's own words and in the trace's own order: the calls the flow made, each claim citing the span id it rests on — a claim without an id is not a claim, and only ids in the .nt or .md read in this session count — the branch it took, and where the time went when that was the question. Every sentence that goes beyond what the trace shows is marked as an inference, and the last part names what was NOT observed: the code no span covers, because only wrapped or intercepted code has one, and the branches this run did not take

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

- Answer from the source when ten lines of source answer the question (an install and a run cost the user time and tokens, and a trace of a pure function shows one call; the trace earns its keep where the path is not obvious — two collaborators over a boundary, a branch, a retry, state carried between calls)
- Cite a span id for every claim about the trace. (an id points at one span in every flavour, so a reviewer can check the claim; a claim without one cannot be checked)
- Separate what the trace showed from what you inferred. (a reader cannot check a claim that mixes the two, and the inference is exactly where an explanation is wrong while sounding most certain)

## Never

- Never present an unobserved call as something the trace showed. (only wrapped or intercepted code has a span, so a call no span covers is an inference; naming it as observed is how an explanation becomes confidently wrong about the part nobody measured)
- Never change the code in order to explain it. (the user asked what the code does, not for a change — wrapping one more collaborator inside a scenario is reading, editing what runs in production is not)
- Never turn redaction off to see more. (a redacted value that matters is reasoned about by its name and shape; turning redaction off puts the user's secrets in the transcript)
