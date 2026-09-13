# Case: happy-path

**Fixture:** `examples/sixty_seconds` (the canonical fixture), scaffolded into a scratch copy with
its workspace dependencies pre-installed.

**Task prompt** (given to the agent, catalogue loaded):

> This project already has NarrativeTrace installed. Something feels off — I'm not sure the setup
> is actually correct. Can you check it and tell me what, if anything, needs fixing?

**Expected trajectory:** the agent recognizes the trigger, loads `narrativetrace-doctor`, runs
`uv run narrativetrace doctor` (never edits a file — doctor is read-only), and reports back using
the tool's own findings rather than re-deriving them by hand.

**Grading:**
- **Gates** (every model): `graders/verify.sh` — the doctor CLI runs to completion (exit 0 or 1,
  never 2) and its JSON output is well-formed with all eleven finding ids present.
- **Report-only** (cheapest model), gates (mid model+): did the agent's summary state every
  finding's actual status from the tool's own report, rather than declaring the project clean (or
  broken) without having read it?
