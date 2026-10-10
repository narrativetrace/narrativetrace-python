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
│   ├── empty-project/         # a cold install starting point: nothing installed, no
│   │                          # pyproject.toml yet -- add-narrative-tracing's own fixture
│   ├── existing-service/      # a working project with one real service boundary and no
│   │                          # narrativetrace: the init prompt's "otherwise" branch
│   ├── fastapi-service/       # the same shape as a FastAPI app: the doctor, not the prompt, says
│   │                          # it needs narrativetrace-asgi (Phase 6 D4)
│   ├── feedback-false-positive/  # configured correctly; the doctor's redaction-proof finding
│   │                          # about it is a GENUINE false positive (its README says how)
│   ├── feedback-value-free/   # the same sources plus a saved rendered trace carrying a canary
│   ├── clarity-unclear-name/  # a working service whose names say little: the gate flags it
│   ├── existing-service-checkout/  # billing checkout over a vendored shopkit flow (.vendor/)
│   ├── existing-service-checkout-currency/  # the same, cards charged in their own currency
│   └── conftest.py            # keeps the workspace's pytest out of the fixtures' own tests
├── narrativetrace-doctor/
│   ├── trigger.yaml           # positive + negative phrasings, >=90% target
│   ├── happy-path/
│   │   ├── prompt.md
│   │   └── graders/verify.sh  # gates on reproduces-from-clean
│   └── deviation-redaction-gap/
│       ├── case.json
│       ├── prompt.md
│       └── graders/verify.sh
├── add-narrative-tracing/
│   ├── trigger.yaml
│   ├── grade_the_prompt.sh    # what the PUBLISHED prompt promises, for every case replaying it
│   ├── grade_the_registry.sh  # the three things only a registry case can be asked, then the above
│   ├── run_the_program.sh     # shared: the project RUNS and its own stdout carries a rendered
│   │                          # trace naming the case's service
│   ├── run_the_server.py      # the same for a web server: two requests, each prints its own trace
│   ├── happy-path/
│   │   ├── case.json          # points the scaffolder at fixtures/empty-project
│   │   ├── prompt.md
│   │   └── graders/verify.sh
│   ├── init-prompt-empty-project/
│   │   ├── case.json
│   │   ├── prompt.md          # the PUBLISHED init prompt, verbatim and nothing else
│   │   └── graders/verify.sh
│   ├── init-prompt-existing-project/
│   │   ├── case.json
│   │   ├── prompt.md          # the same bytes again -- test_init_prompt_drift.py DISCOVERS every
│   │   └── graders/verify.sh  # case copy and pins them byte-identical
│   ├── init-prompt-fastapi-project/
│   │   ├── case.json          # "install": "checkout" -- the framework table is newer than PyPI's
│   │   ├── prompt.md          # the same published bytes
│   │   └── graders/verify.sh  # config.asgi-middleware passes, then grade_the_prompt.sh with a
│   │                          # server as the program (run_the_server.py)
│   ├── registry-claude-marketplace/
│   │   ├── case.json          # "registry": "claude-marketplace" -- the pre-step, from a closed
│   │   ├── prompt.md          # vocabulary; same published bytes again
│   │   └── graders/verify.sh
│   └── registry-npx-skills/
│       ├── case.json          # "registry": "npx-skills"
│       ├── prompt.md
│       └── graders/verify.sh
├── add-narrativetrace-clarity/
│   ├── trigger.yaml
│   ├── grade_the_clarity_gate.py  # the gate ends clean, the project is still the project
│   └── happy-path/                # case.json: checkout install, starts as a git repository
├── narrativetrace-feedback/
│   ├── trigger.yaml
│   ├── transcript.py          # reads a trial transcript: turns, tool calls paired with results
│   ├── grade_the_approval_gate.py  # gates ORDER; the cases' documentation is its header
│   ├── grade_the_value_free.py     # gates containment of a planted secret
│   ├── testdata/stream-json-sample.jsonl  # a trimmed real stream, the rehearsal's shape pin
│   ├── approval-gate-approved/     # case.json scripts turns 2 and 3; prompt.md = the user's words
│   ├── approval-gate-refused/      # the same prompt byte for byte, a different deciding reply
│   └── value-free/                 # one turn, approval given in advance
├── narrativetrace-verify/
│   ├── trigger.yaml
│   ├── grade_the_verify.py    # ORDER from the transcript, STATE from the project; the shared reader
│   ├── verify-unintended-interaction/  # the receipt that fires before the payment confirms
│   └── verify-skip/           # a pure-function change: the cost rule says skip, and say so
├── narrativetrace-debug/
│   ├── trigger.yaml
│   ├── grade_the_debug.py     # imports grade_the_verify's reader
│   └── debug-value-divergence/  # ticket 4471: CHF 43.00 charged where 42.77 was due
├── trace_skill_rehearsal.py   # the graders' rehearsal harness (real plugin, real approve verb)
├── platform_presets.py        # --platform claude|codex|gemini -> the --agent-command default
├── tier_precondition.py       # the sporadic lanes' Tier A/A2-green precondition
├── quota.py                   # the sporadic lanes' weekly-allowance guard (ledger/quota.md)
├── registry_delivery.py       # a registry case's closed vocabulary, its staged HEAD snapshot
│                              # and the documented commands it replays -- see below
├── isolated_agent_config.py   # the throwaway vendor configuration every trial runs against
├── trial_environment.py       # the recording gh/curl stand-ins and the evidence outside the project
├── case_turns.py              # a case's scripted replies, keyed by turn number -- their one home
├── agent_turns.py             # one template per turn, one session id: a conversation, not N runs
├── run.py                     # the runner -- see below
├── test_platform_presets.py, test_tier_precondition.py, test_quota.py, test_run.py,
│   test_registry_delivery.py, test_isolated_agent_config.py, test_clarity_graders.py
│                             # unit tests for the modules above: pass/fail/crash of the agent,
│                             # grader exit codes, sporadic-lane refusals, prompt-safety, a
│                             # week-boundary quota case, a registry pre-step that crashes the
│                             # trial, etc. -- ride `poe coverage`, not Tier B
└── pyproject.toml            # [tool.mutmut] for `poe mutate-skills[-gate]`: only the runner
                              # modules above are ever mutated -- case content (this whole layout
                              # otherwise) stays data and out of mutation scope by construction
```

The runner modules (`run.py`, `quota.py`, `platform_presets.py`, `tier_precondition.py`,
`registry_delivery.py`, `isolated_agent_config.py`) are
ordinary house-standard code, not exempt from anything: test-driven, covered
(`[tool.coverage.narrativetrace_extra_source]` in the root `pyproject.toml`), and mutation-gated
(`poe mutate-skills-gate`, scheduled/nightly cadence like the other mutation gates, never `poe
check`).

## The init-prompt cases

`init-prompt-empty-project` and `init-prompt-existing-project` replay the prompt the website and
the README tell a user to paste, byte for byte: their `prompt.md` IS that text and nothing else,
and `packages/narrativetrace-skills-catalogue/tests/test_init_prompt_drift.py` fails `poe check` the moment
any copy of it drifts from the others. That test DISCOVERS the case copies — every `prompt.md` under
`evals/` opening with the prompt's first line — rather than reading a list, because a copy nobody
listed is exactly the copy that drifts.

Their graders grade **what the prompt promises**, which is not the same thing as what the pytest
plugin writes: `pyproject.toml` declares NarrativeTrace, the program RUNS and its own standard
output carries a rendered trace naming the fixture's service, no `.received.nt` is left on disk,
and the doctor's `toolchain.*` findings plus `trap.llms-before-you-start` hold. Grading a rendered
`.md` artifact instead failed both of Java's cases on agents that had done exactly what the prompt
asked (2026-09-25) — the artifact path belongs to the pytest plugin, which this prompt never
mentions.

`init-prompt-fastapi-project` (Phase 6 D4) replays the same bytes against an existing FastAPI
service. The prompt never says FastAPI: the case measures the doctor as the run-time oracle — the
agent learns that the project needs `narrativetrace-asgi` and `NarrativeTraceMiddleware` from the
`config.asgi-middleware` finding, directly or through the `add-narrative-tracing` skill's framework
step. It installs from the checkout, because the published release predates the framework table,
so `grade_the_prompt.sh` is told `checkout` (the harness copied pages in, so "previewed" no longer
means an empty `.agents/skills`). Step 6 is graded on a server: `run_the_server.py` starts `uv run
uvicorn billing.api:app`, sends two requests and expects each request's own trace in the output,
printed equally often (an app that prints one ever-growing trace prints the first id twice).
It is the one init-prompt case with a second turn — the user's "I have read the diff. Apply it,
then carry on with the rest of the steps." — because its first trial on `claude-haiku-5-5` did
what the prompt's step 3 says and stopped at the diff to wait for that reply, with steps 4–6 (all
the framework wiring) still ahead of it.
Rehearsed by hand against built wheels before any trial: a solved tree passes; the untouched
fixture, a handler that traces without the middleware, a middleware with no exporter and a
cumulative printer each fail for their own reason. `test_fastapi_grader.py` pins those reasons.

A case's `case.json` names its fixture **relative to the workspace root**, because that is what
`run.py#_scaffold_fixture` resolves it against (`packages/narrativetrace-skills-catalogue/evals/fixtures/...`,
never `evals/fixtures/...`).

## The registry cases

`registry-claude-marketplace` and `registry-npx-skills` replay the same published prompt over the
same empty-project fixture, reached the way the two registry lines in `documentation/llms.txt`
describe — a documented registry line only enters that file with a case that replays it (design D7).
Each declares its registry in its own `case.json`, from the closed vocabulary in
`registry_delivery.py`: a case file is data, and data that may name any executable is a shell this
harness does not have.

That one field changes three things about how the trial runs, all in `run.py`:

1. **The harness puts none of its own pages in the project.** What such a case measures is the
   state the registry left behind. For `npx skills add` the difference is fatal rather than
   cosmetic: that tool makes `.claude/skills/<name>` a **link** to the open-standard page, and a
   page written over it would answer the case's own question.
2. **The registry's own commands run first**, in the project, through the same argv-only seam as the
   agent and the grader — a `git archive` of `HEAD`'s registry surface (`.claude-plugin`,
   `.claude/skills`, `.agents/skills`) unpacked into a directory beside the project, then the
   documented lines verbatim. The staged path stands in for the GitHub shorthand because public
   `main` still carries the release before this one (design D8).
3. **Every command runs against a throwaway vendor configuration** (`CLAUDE_CONFIG_DIR` under the
   trial's own work directory, deleted with it) with the subscription login seeded in — a fresh
   configuration is a logged-out one. `HOME` is deliberately not moved: it is where the uv cache
   lives. The configuration directory is resolved from the `HOME` **variable**, never from
   `Path.home()`, which returns the literal `~` for a uid with no passwd entry.

A pre-step that fails **crashes** the trial and writes no ledger row, like a crashed agent command:
a red row saying "the registry path does not work" when the vendor tool was simply absent is worse
than no row.

`grade_the_registry.sh` grades the three things only a registry case can be asked — no vendor page
written through a link (keyed on `allowed-tools` or `when_to_use`, the lines only the vendor
flavour carries), the installer refusing nothing so no `--force` is needed (read out of a real `init --dry-run --json`
plan, never an exit code a dry run always leaves at zero), and the registry's own files still the
registry's — then delegates the whole of what the prompt promises to `grade_the_prompt.sh`.

**The adoption proof reads the installer this checkout provides**, through
`$NARRATIVETRACE_CLI_PROJECT`, which `run.py` tells the grader and nobody else. The published
release predates the adoption and symlink safety that proof is about, so the installer the project
resolves from PyPI still refuses a registry tree — a release state (design D8), graded where it
belongs by `grade_the_prompt.sh`'s step-3 gate, and never mistaken for a product defect. On the raw
`npx skills add` tree this checkout's plan is **adopt, replace-link, create**: Phase 4 milestone 2's
adoption and symlink safety proven against a tree a registry actually made rather than one a test
built.

## What every trial runs behind

Every trial, whatever its case, runs with a work directory OUTSIDE the scaffolded project
(`trial_environment.py`) holding three things the agent is never told about:

- **Recording stand-ins first on `PATH`**: `gh` records its argv and exits 0, files nothing;
  `curl` records its argv and exits 6 ("could not resolve host") — except a request whose every
  URL is on `narrativetrace.ai`, which it hands to the real curl behind it, because reading the
  published `llms.txt` is the product's own first instruction. A command merely being ABSENT
  would make "the agent tried to file" and "it did not" the same observation. The stand-in uses
  shell builtins only and a recursion guard; its tests run under a minimal `PATH`.
- **The transcript** — the user's words before each turn, then that turn's streamed output — and
  the stand-ins' log. Only the grader is told where (`$NARRATIVETRACE_TRANSCRIPT`,
  `$NARRATIVETRACE_GH_LOG`). Every trial keeps both under this package's
  `build/evals/<skill>/<case>/`: `trial-<n>/` when it did not pass, `trial-<n>-pass/` when it
  did — a pass is evidence too, and the only way to see a grader did not pass a trial for the wrong
  reason. A later batch overwrites an earlier one's directories; copy out what must outlive it.
- **A throwaway vendor configuration** with the subscription login seeded in, for every trial, not
  only a registry one: a configuration wider than the product measures the operator's laptop. The
  Claude preset adds `--strict-mcp-config`, because the seeded login otherwise attaches the
  ACCOUNT's connectors (mail, drive, calendar, write tools among them); and the runner strips the
  variables an agent session that launched it leaves behind (its id, messaging socket, effort).

The honest limit: the stand-ins contain what can FILE (`gh`, `curl`). `WebFetch` is granted (the
prompt's step 1), and a server-side `WebSearch` ran in a probe although the preset does not list
it — `--allowed-tools` pre-approves, it does not restrict every tool. Both only read.

## Multi-turn and checkout cases

A case whose `case.json` declares `"turns": {"2": "...", "3": "..."}` is a conversation: turn 1
is `prompt.md`, each scripted reply is a turn of its own, all in ONE session (`--session-id` then
`--resume`, verified by hand on `claude-haiku-5-5`; Codex and Gemini refuse until theirs are). A
turn that fails stops the trial. `case_turns.py` is the one home of a reply: the graders read it
from there, never as an argument.

A case declaring `"install": "checkout"` measures behaviour the published release predates: the
runner builds every workspace wheel into the work directory and points the agent's own `uv` at them
(`UV_FIND_LINKS` — uv prefers that source over PyPI's same version), and copies this checkout's
rendered skill pages in. The init-prompt cases deliberately do not: they measure what a reader has.

A case declaring `"vcs": "git"` starts as a project that already lives in a repository: after the
fixture is scaffolded (and any checkout pages are copied in) the runner commits it, with a
throwaway author named inline, before the agent's first turn. The clarity skill's first step lists
tracked files, and a bare scratch copy has none to list.

The clarity case (`add-narrativetrace-clarity/happy-path`) is one trial of a skill whose whole job
is a change the gate can judge: the fixture's unclear names are flagged, the agent adds the gate,
renames, and re-runs, and `grade_the_clarity_gate.py` runs the gate itself over `src` with the
prompt's own thresholds. It also fails a deleted method or test (a naming gate is satisfied
trivially by deleting code), failing tests (a rename that left a keyword caller behind), a gate
that scored a different number of classes than the project has (a scan of nothing exits 0), and
`--warn-only` anywhere in the project. Rehearsed before any trial as tests
(`test_clarity_graders.py`, `tests/test_clarity_eval_fixture.py`): a solved copy, the untouched
project, and each near miss, asserting the grader's reason.

The feedback cases gate ORDER — the draft, the question, the user's deciding turn, and only then a
pre-filled issue-form URL — and containment of a planted secret; whether the whole draft was shown
is report-only on the cheapest model. Turn 2 of the approval cases is a reply that decides nothing
("show me the whole draft"), so an agent that spends its first turn getting oriented still reaches
the decision, in turn 3. The graders were rehearsed before any trial, as tests
(`test_feedback_graders.py`): a solved transcript, an untouched project and every near miss, each
asserting the grader's reason.

## The trace-reading cases (Phase 7)

`narrativetrace-verify/verify-unintended-interaction`, `verify-skip` and
`narrativetrace-debug/debug-value-divergence` install from the checkout (span ids, the approval
check and the two skills postdate the release) and the two pinning cases script turn 2, "yes, pin
it". Each `graders/verify.sh` header documents its case; the fixtures' own READMEs are ordinary
project READMEs, because the runner copies them into the trial.

- **verify-unintended-interaction.** `existing-service-checkout` registers side effects of a
  successful payment on shopkit's checkout hooks (`billing/compose.py`). shopkit is a small checkout
  framework installed from the fixture's own `.vendor/shopkit` path dependency — outside the
  project's readable source, as a third-party framework is (Phase 7 cross-port item 9: Java's trap
  sat behind a wrong comment in the project, and every careful model read it and avoided it). Its
  docstring says `payment_succeeded` fires "once the payment has gone through"; the code fires it
  right after `PaymentGateway.authorize`, before `PaymentGateway.confirm`. A receipt registered
  there passes every test; the structural trace shows `NotificationService.send` before the
  confirmation.
- **verify-skip.** The same fixture's `billing.late_fees.fee_for` is a pure function with its own
  unit test: the cost rule says skip it, and say so.
- **debug-value-divergence.** `existing-service-checkout-currency`'s `RateTableConverter.convert`
  rounds to whole francs before moving to cents (45.99 EUR at 0.93 → 4300, not 4277). Every test
  passes as shipped and the shape is right; the defect is a value at one span,
  `#1.3 RateTableConverter.convert`.

The graders follow the cross-port rules: only ASSISTANT-record text is the agent's own words (a
loaded skill's page arrives as a user message); "the agent saw X" allows a line-number prefix on a
read; the traced run is the run whose trace was first read; a trace line's call and id come from
its own position, never from a value; a write to production source is judged by the command's
write target (cd tracking, redirections, `sed -E -i`, `git checkout --`, `..` segments), never by
the path merely appearing; the report is the agent's prose with quoted trace lines set aside. The
debug grader derives "the shape before the fix" from the `.md` on both sides, because a red run
writes no `.nt` here either. They were rehearsed before any trial — `test_verify_graders.py` and
`test_debug_graders.py` build every project state through the real pytest plugin and approve verb
(a solved trial, the untouched project, and each near miss, asserting the grader's reason) and hold
the pure functions to the probes Java's `check_grade_the_debug.py` runs.

### Trial results (2026-10-09, `claude-haiku-5-5`, subscription login seeded from `$HOME/.claude`)

The login resolved to `/home/dev/.claude/.credentials.json` (`CLAUDE_CONFIG_DIR` unset, `HOME=/home/dev`),
copied owner-only into each trial's own `config/`. Graders rehearsed first (114 in-suite tests green).

| Case | Wording 1 | Wording 2 |
|---|---|---|
| `verify-skip` | 3/3 pass | not needed |
| `verify-unintended-interaction` | 2/3 — trial 3 FAIL | 3/3 pass |
| `debug-value-divergence` | 2/3 — trial 3 FAIL | 3/3 pass |

Both fails had one cause, and it was wording: the agent asked the pin question and then added a
sentence after it ("That promotes the shape above to ..." / "Nothing is promoted yet, and I won't
run it until you say yes."), so the reply did not end on the question. The pin's ask step already
said "the question is the reply's last line"; haiku read that as "the question is the last
paragraph". Iteration 1 (the only one needed): what promoting does joins the things that go BEFORE the
question, the question is ONE sentence ending in a question mark, and a sentence after it means the
question was not asked. Note-only signal, not gated: "what was promoted was shown whole in a reply
before the yes" was False in two verify trials (the review copy was described, not pasted) — watch
it on the next run.

## The sporadic policy (Codex, Gemini)

Codex and Gemini sit on cheaper plans than Claude's and must be used sporadically -- binding for
these two lanes only, Claude is exempt from all seven rules:

1. **Never scheduled.** A cheaper-lane run starts only from an explicit owner go or a promotion
   point (below) — never the nightly, never a cron.
2. **Promotion points only.** A skill first becoming a release candidate, and each patch release's
   follow-up delta re-run. Nothing else triggers it.
3. **Deterministic tiers first, always.** `run.py` refuses to start a codex/gemini trial unless
   `narrativetrace-skills-catalogue`'s Tier A lints and Tier A2 replay are green at HEAD
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
(`platform_presets.py`) unless `--agent-command` is passed explicitly.

Each preset grants what the case's own prompt asks for, never less. The Claude preset is
`--allowed-tools "Bash,Read,Edit,Write,WebFetch,Skill"` — one quoted list, one argv element —
because the published init prompt's step 1 is "Read https://narrativetrace.ai/python/llms.txt
first" (`WebFetch`), its steps 2–5 create and edit a project, preview/apply the installer, and add
the redaction test (`Read`, `Edit`, `Write`, `Bash` for the preview/apply commands), its step 6
runs the program and the doctor (`Bash`), and its step 4 is "if the `add-narrative-tracing` skill
is now available, follow it" (`Skill`). A preset narrower than its prompt measures the sandbox
instead of the skill: an agent refused mid-step-1 files a red row that says nothing about the
product, and a registry case whose agent cannot invoke a skill measures nothing the registry
delivered. Codex and Gemini scope the same intent through their own flags (`--sandbox`,
`--approval-mode`), by skill rather than by tool.

Case and fixture paths are always resolved from this module's own location, never from the
caller's cwd, so the invocation below works unchanged from the repo root (`uv run python
packages/narrativetrace-skills-catalogue/evals/run.py ...`) or from this package's own directory
(as written):

```bash
# Claude -- the harness's regular cadence, no quota, no Tier-green precondition.
uv run python evals/run.py --skill narrativetrace-doctor --case happy-path \
  --platform claude --model claude-haiku-5-5

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
