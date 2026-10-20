# Case: existing-service

**Fixture:** `evals/fixtures/existing-service-pytest` (a service WITH a pytest suite and no
NarrativeTrace), scaffolded into a scratch copy with nothing installed yet.

**Task prompt** (given to the agent, catalogue loaded):

> This service already has a test suite. Add NarrativeTrace and show me the trace of one of my
> existing tests — I want to find the file afterwards, not just see it scroll by.

**Expected trajectory:** the agent loads `add-narrative-tracing`, adds `narrativetrace` and the test
integration, runs one existing test through it with output on — the page's tests branch, not a demo
script — prints the rendered file, and runs `uv run narrativetrace doctor`. It adds no second test
runner.

**Grading:**
- **Gates** (every model): `graders/verify.sh` — the grader runs the project's tests itself
  (`uv run pytest -q`) and they pass, including the fixture's own test; at least one `.md` AND one
  `.nt` exist under the integration's output directory (`narrative-traces/`); and every
  `toolchain.*` doctor finding holds.
- **Report-only** (cheapest model), gates (mid model+): did the agent finish with the doctor's
  report read rather than declaring success unprompted?
