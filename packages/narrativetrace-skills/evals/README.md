# Tier B — LLM trials

Engine-neutral cases: fixture + task prompt + world-state verifier, portable by construction.
**Never run in `poe check`** — Tier A (lints) and Tier A2 (oracle replay) ride `check` every
commit; Tier B runs through the subscription CLIs, on the regular nightly cadence for the Claude
lane, sporadically (below) for Codex/Gemini, and change-triggered (not scheduled) for a patch
release's follow-up delta.

## Layout

```
evals/
├── fixtures/
│   ├── redaction-gap/         # deviation fixture: a project with a sensitive param and no
│   │                          # redaction-proof test -- the canonical fixture is
│   │                          # examples/sixty_seconds itself, used directly for the happy path
│   └── empty-project/         # a cold install starting point: nothing installed, no
│                              # pyproject.toml yet -- add-narrative-tracing's own fixture
├── narrativetrace-doctor/
│   ├── trigger.yaml           # positive + negative phrasings, >=90% target
│   ├── happy-path/
│   │   ├── prompt.md
│   │   └── graders/verify.sh  # gates on reproduces-from-clean
│   └── deviation-redaction-gap/
│       ├── prompt.md
│       └── graders/verify.sh
├── add-narrative-tracing/
│   ├── trigger.yaml
│   └── happy-path/
│       ├── case.json          # points the scaffolder at fixtures/empty-project
│       ├── prompt.md
│       └── graders/verify.sh
├── platform_presets.py        # --platform claude|codex|gemini -> the --agent-command default
├── tier_precondition.py       # the sporadic lanes' Tier A/A2-green precondition
├── quota.py                   # the sporadic lanes' weekly-allowance guard (ledger/quota.md)
├── run.py                     # the runner -- see below
├── test_platform_presets.py, test_tier_precondition.py, test_quota.py, test_run.py
│                             # unit tests for the four files above: pass/fail/crash of the agent,
│                             # grader exit codes, sporadic-lane refusals, prompt-safety, a
│                             # week-boundary quota case, etc. -- ride `poe coverage`, not Tier B
└── pyproject.toml            # [tool.mutmut] for `poe mutate-skills[-gate]`: only the four runner
                              # files above are ever mutated -- case content (this whole layout
                              # otherwise) stays data and out of mutation scope by construction
```

The four runner files (`run.py`, `quota.py`, `platform_presets.py`, `tier_precondition.py`) are
ordinary house-standard code, not exempt from anything: test-driven, covered
(`[tool.coverage.narrativetrace_extra_source]` in the root `pyproject.toml`), and mutation-gated
(`poe mutate-skills-gate`, scheduled/nightly cadence like the other mutation gates, never `poe
check`).

## The sporadic policy (Codex, Gemini)

Codex and Gemini sit on cheaper plans than Claude's and must be used sporadically -- binding for
these two lanes only, Claude is exempt from all seven rules:

1. **Never scheduled.** A cheaper-lane run starts only from an explicit owner go or a promotion
   point (below) — never the nightly, never a cron.
2. **Promotion points only.** A skill first becoming a release candidate, and each patch release's
   follow-up delta re-run. Nothing else triggers it.
3. **Deterministic tiers first, always.** `run.py` refuses to start a codex/gemini trial unless
   `narrativetrace-skills`' Tier A lints and Tier A2 replay are green at HEAD
   (`tier_precondition.py`) — a Tier B trial on a skill whose replay is red is quota burned on a
   known defect.
4. **Smallest sample that answers the question.** Per skill per platform per promotion point: one
   trigger sample, one happy-path case, one deviation case, `n = 1`, cheapest model. `n = 3` only
   when a case FLIPS (green on Claude, red here).
5. **A weekly allowance per platform, in a ledger the runner reads.** `ledger/quota.md`: plan
   tier, weekly allowance, and every run's spend appended by `run.py`. The runner refuses a
   platform whose allowance is spent and says so; **there is no override flag** — the owner edits
   the ledger.
6. **A cheaper-lane red never blocks.** It files a finding the next Claude-lane run and the
   skill's author read. Shipping requires Claude green; Codex/Gemini status may be `pending` at
   ship time.
7. **Cheapest model per platform, fixed in the ledger.** A skill that passes only on a stronger
   model is a defect signal for the skill's code layer, not a reason to raise the model.

Codex defaults to the same allowance the TypeScript reference uses (basic plan, 4 cases/week);
Gemini stays at 0 — the `gemini` preset is built but every trial refuses — until the CLI is
installed, signed in, and the owner raises the allowance in `ledger/quota.md`.

## Running a trial

`run.py` scaffolds a case's fixture into a fresh temp copy outside every repo tree, drives the
requested agent CLI against the prompt with the catalogue loaded, runs the case's grader, and
appends one row to `ledger/runs.jsonl`. It is never invoked by `check`; the owner runs it by hand
or from the nightly job. `--platform` fills `--agent-command` with that platform's preset
(`platform_presets.py`) unless `--agent-command` is passed explicitly. Case and fixture paths are
always resolved from this module's own location, never from the caller's cwd, so the invocation
below works unchanged from the repo root (`uv run python packages/narrativetrace-skills/evals/run.py
...`) or from this package's own directory (as written):

```bash
# Claude -- the harness's regular cadence, no quota, no Tier-green precondition.
uv run python evals/run.py --skill narrativetrace-doctor --case happy-path \
  --platform claude --model haiku

# Codex -- sporadic: refuses unless Tier A/A2 are green and the weekly allowance isn't spent.
uv run python evals/run.py --skill narrativetrace-doctor --case happy-path \
  --platform codex --model <the plan's cheapest/mini model>

# Gemini -- same guards; refuses today (allowance 0 until the CLI is installed).
uv run python evals/run.py --skill narrativetrace-doctor --case happy-path \
  --platform gemini --model flash
```

Each CLI runs headless, on its own subscription login — the harness never passes an API key. Every
run is noted in `ledger/runs.jsonl` regardless of outcome (a codex/gemini trial also appends a
spend row to `ledger/quota.md`); `ledger/promotion.md` is the regenerated skill × platform matrix
(`scripts/promotion_render.py`, drift-checked in `poe check` the way `SKILL.md` is), cleared on a
wording or fixture change.

**Prompt safety.** The prompt is never spliced into a shell command line: it reaches the agent CLI
as one argv element (built with `subprocess.run`, no `shell=True`), so backticks, `$(...)`, quotes,
and newlines in it are inert.

## What gates, what doesn't

- **Gates** (every model): the install/diagnosis reproduces from clean, the CLI's exit code and
  JSON shape match what the case expects, no crash.
- **Report-only** (cheapest model), **gates** (mid model and above): judgment measures — whether
  the agent's *interpretation* of a finding was sound, not just whether doctor ran.
