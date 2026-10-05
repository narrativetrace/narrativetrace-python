# Case: happy-path

**Fixture:** `evals/fixtures/empty-project` (a cold install from an empty directory), scaffolded
into a scratch copy with nothing installed yet.

**Task prompt** (given to the agent, catalogue loaded):

> This is a brand new Python project. I want to add NarrativeTrace and see a trace from a real
> method call within the next few minutes.

**Expected trajectory:** the agent recognizes the trigger, loads `add-narrative-tracing`, installs
`narrativetrace` with `uv add narrativetrace` (creating a `pyproject.toml` in the process), wraps an
object with `trace_object`, runs it, and shows the rendered trace — then runs `uv run
narrativetrace doctor` and reports its findings rather than declaring success unprompted.

**Grading:**
- **Gates** (every model): `graders/verify.sh` — `pyproject.toml` exists and declares
  `narrativetrace` as a dependency, the script prints a rendered trace line, and every
  `toolchain.*` doctor finding holds.
- **Report-only** (cheapest model), gates (mid model+): did the agent run the final
  `narrativetrace doctor` seam step and read its report, rather than declaring the project done
  unprompted?
