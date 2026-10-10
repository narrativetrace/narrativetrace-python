# Agent skills

NarrativeTrace ships **skills**: agent-loadable procedures that run tested commands and gate
completion on a `verify` step, rather than docs an agent might or might not read. A skill is thin
by design — the checking, diagnosis, or generation logic lives in tested library code; the skill's
own job is knowing when to act, invoking that tested code, and interpreting the result in context.

## Six skills: setup, diagnosis, clarity, reporting, verification, and debugging

- **`add-narrative-tracing`** — installs NarrativeTrace into a project and gets it to a first
  trace: install with the real toolchain (`uv add narrativetrace`), wire the frameworks the project
  already uses by applying every `config.<framework>-*` fix the doctor prints (the installed
  doctor's own framework table decides which, so the skill page names none), wrap an object,
  render and run the first trace, then wire a real logger (the stdlib `logging` bridge). Runs `uv run
  narrativetrace doctor` and hands off — the seam between the two skills — then ends by
  *previewing* (never applying) `narrativetrace init`, so the next session finds these skills
  already installed without being told about them.
- **`narrativetrace-doctor`** — diagnosis only, and **read-only**: it never edits, generates, or
  deletes a file. Runs the tested CLI, reads its report, and walks through the parts a plain CLI
  output can't cover on its own: proving redaction in a test, reading a rendered trace before
  asserting against it, and the approval-trace flow (flagged unstudied — its own eval cell is
  still pending).
- **`add-narrativetrace-clarity`** — adds the naming-clarity gate to a project and works it to
  clean: installs `narrativetrace-clarity` as a development dependency (`uv add --dev`), scans the
  project's packages, checks the report is **fresh and scored at least one class** — the scan exits
  `0` and writes nothing when it finds no class, so an old report would otherwise pass for a new
  one — renames what the report flags (in `snake_case`, whatever case the suggestion's examples
  use), runs the project's tests, and re-runs the gate with the project's own thresholds until it
  exits `0`. It never lowers a threshold, never adds `--warn-only`, and never harvests a glossary
  just to read vocabulary. This runtime's gate reads Python source, so there is no test-runner
  path; a project that commits a glossary runs the same scan through `narrativetrace_glossary.clarity_scan`.
- **`narrativetrace-feedback`** — reports a defect in NarrativeTrace itself: a doctor check that is
  wrong or whose fix does not work, a skill step that cannot be followed, wording in the install
  prompt that led somewhere wrong, or the library misbehaving on a correctly configured project.
  The tested verb behind it drafts the report from the project (the install coordinates, the
  doctor's own JSON report, and at most one structural trace), and **refuses to write a report that
  carries a value from your traces** — naming the rule that refused it, so there is something
  specific to fix rather than a warning to ignore. The skill then shows the whole draft and asks
  once whether to file it publicly. It sends nothing anywhere and files nothing without an answer
  given in a turn of its own.
- **`narrativetrace-verify`** — reads what a change actually did before the agent says it is done.
  It runs after the tests are green and first decides whether the change is worth tracing at all —
  a pure function or a one-class edit is not, and the skill says so and stops. Otherwise it writes
  the intent down before anything runs (which collaborators, in which order, under which branch,
  how many times), runs the smallest real path with tracing on (a test using the `narrative_trace`
  fixture), reads the value-free structural trace against that intent, opens values only on the
  span that looks wrong, fixes and re-reads, then pins the flow as an `.approved.nt` baseline —
  turning approval mode on if it is off, running the whole suite in approval mode, showing the
  whole `.received.nt`, and promoting it with `narrativetrace-approve` only after your yes, in a
  turn of its own. Its report cites span ids (`#2.1`), the position every flavour prints for the
  same call, so a claim about the trace can be checked against the trace.
- **`narrativetrace-debug`** — finds the cause of a wrong result by reading what the code did with
  the values, not by stepping through it. It starts from a symptom rather than a change: reproduce
  it with the smallest input and tracing on, read the sequence diagram first when the path crosses
  threads or tasks, then name — by span id, before touching any code — the first span whose inputs
  are right and whose result is wrong. It narrows by span, never by file: it reads the sub-tree under
  that id and, when the work inside the span is not traced, wraps one more collaborator with
  `trace_object` rather than redacting anything (`not_traced_field`, `__nt_not_traced__` and
  `@not_traced` hide a value; they do not scope a trace). It fixes the defect in that span, re-runs
  the same input, and checks that nothing else moved — a red run writes no `.nt`, so the shape
  before the fix is the reproduction's Markdown call lines without their values. It keeps the
  reproduction as a regression test, pins its structural trace through the same approval gate as
  `narrativetrace-verify`, and reports the root cause by span id. When the trace and the code
  disagree, or the defect is NarrativeTrace's own, it hands off to `narrativetrace-feedback`
  instead of patching around it.

They compose: a brand-new project starts with `add-narrative-tracing`; a project that already has
NarrativeTrace installed, where something isn't working, starts with `narrativetrace-doctor`.
Either path ends at the doctor — it owns diagnosis from there. `add-narrativetrace-clarity` owns
the naming report and its gate; it does not install tracing. `narrativetrace-feedback` is where a
path ends when the problem turns out to be ours rather than the project's — the doctor's own
closing rule points at it. `narrativetrace-verify` is what a session with NarrativeTrace installed
does after every change worth tracing — the install skill's last step points the next session at
it, and the doctor's `config.approval-mode` finding (baselines that nothing compares) is fixed by
its pin step. `narrativetrace-debug` is where a reported symptom starts; it shares the verify
skill's reading reference (which flavour answers which question, and the shapes that mean
something went wrong) and its pin, and ends at `narrativetrace-feedback` when the defect is ours.
A later skill will own generation (writing the redaction-proof test the
doctor can only ask you to add today).

## The `narrativetrace` CLI

The first two skills run `uv run narrativetrace doctor` — the free CLI's `doctor` verb, alongside
`init`/`uninstall` ([Installing them](#installing-them), below), `feedback` (the verb behind
`narrativetrace-feedback`) and the existing `narrativetrace-approve` console script.
`doctor` is read-only, zero network, `--json` for machine output, exit `0` (clean), `1` (findings),
or `2` (could not run). Nineteen checks with stable, dotted ids: interpreter/pytest versions
against what's declared, the eight `narrativetrace-*` packages agreeing on one version,
`NARRATIVETRACE_OUTPUT`'s spelling, the pytest plugin's registration, whether the NarrativeTrace
agent skills are installed and current, unrecognized `narrativetrace.toml` keys, an
imported-but-unused redaction marker, a `*args` method's parameters collapsing to one
`args: [...]` value, whether redaction is proven in a test, stale approval-trace diffs, approved
baselines nothing compares because approval mode is off, and one
`config.<framework>-*` check per row of the framework table (the table and each row's wiring are
in [`llms-full.md`](llms-full.md#framework-table--what-the-doctor-checks)): a framework the project
uses whose integration is not added, or added but never wired, fails with the lines to add; a
framework with no integration shipped is reported, never guessed at.

`feedback draft | url | gh` has three channels over one report. `draft` writes the report under
`build/narrativetrace/feedback/` and prints all of it; `url` prints the pre-filled issue-form URL
for `github.com/narrativetrace/narrativetrace-python`, which you open and submit under your own
account; `gh` prints the exact `gh issue create` line, only when `gh` is installed and signed in,
and never runs it. Each channel re-drafts from the flags it is given, so nothing is filed under a
draft that changed after it was shown. Exit `0` (drafted), `1` (the channel is not available, or the filesystem refused the
files), or `2` (a `vf.*` value-free rule refused the report, and nothing was written; or the
command line could not be read). Filing is public: it
shows that your project uses NarrativeTrace.

## Installing them

The `narrativetrace` package (already on your `PATH` as `uv add narrativetrace` puts it there)
carries an `init` verb that installs all six skills for you — zero network, and nothing written until
you say so:

```bash
uv run narrativetrace init --dry-run
```

<!-- snippet: examples/sixty_seconds/build/agent-skills-init-preview.json -->
```json
{
  "carrier": "narrativetrace-skills==0.3.0",
  "actions": [
    {
      "kind": "create",
      "path": ".agents/skills/narrativetrace-doctor/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": ".agents/skills/add-narrative-tracing/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": ".agents/skills/narrativetrace-feedback/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": ".agents/skills/add-narrativetrace-clarity/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": ".agents/skills/narrativetrace-verify/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": ".agents/skills/narrativetrace-debug/SKILL.md",
      "status": "planned"
    },
    {
      "kind": "create",
      "path": "AGENTS.md",
      "status": "planned"
    }
  ],
  "exit_code": 0
}
```
<!-- /snippet -->

That is the `--json` envelope; without the flag the same command prints the plan as a unified
diff. Read it, then run it again without `--dry-run` to write `.agents/skills/` (and
`.claude/skills/` too, once this project has a `.claude/` directory or `CLAUDE.md`, or with
`--vendor claude`) plus one marked section in `AGENTS.md`. `narrativetrace uninstall` removes
exactly what it wrote and nothing else; `narrativetrace doctor`'s `config.skills-installed` check
reports when what's installed is stale, so keeping it current later is `init --dry-run` again, not
a byte-for-byte re-copy.

Copying the rendered files by hand still works, and is the fallback for a platform without its own
discovery convention, or before you have added the `narrativetrace` package at all:

- **Claude Code**: rendered `SKILL.md` files live at
  [`.claude/skills/add-narrative-tracing/`](../.claude/skills/add-narrative-tracing/SKILL.md),
  [`.claude/skills/narrativetrace-doctor/`](../.claude/skills/narrativetrace-doctor/SKILL.md),
  [`.claude/skills/narrativetrace-feedback/`](../.claude/skills/narrativetrace-feedback/SKILL.md),
  [`.claude/skills/add-narrativetrace-clarity/`](../.claude/skills/add-narrativetrace-clarity/SKILL.md),
  [`.claude/skills/narrativetrace-verify/`](../.claude/skills/narrativetrace-verify/SKILL.md) and
  [`.claude/skills/narrativetrace-debug/`](../.claude/skills/narrativetrace-debug/SKILL.md) in
  this repository — the directory name and the frontmatter `name:` are always the catalogue's
  canonical id, never a shortened segment: a repo-level `.claude/skills/` directory is a flat
  namespace, not a Claude Code plugin, so a shortened name (`doctor`) would collide with every other
  vendor's skill of that name. Copy any directory into your own project's
  `.claude/skills/<name>/` and Claude picks it up on its own, invokable by name
  (`add-narrative-tracing` / `narrativetrace-doctor` / `narrativetrace-feedback` /
  `add-narrativetrace-clarity` / `narrativetrace-verify` / `narrativetrace-debug`) directly.
- **Codex CLI**: rendered `SKILL.md` files live at
  [`.agents/skills/add-narrative-tracing/`](../.agents/skills/add-narrative-tracing/SKILL.md),
  [`.agents/skills/narrativetrace-doctor/`](../.agents/skills/narrativetrace-doctor/SKILL.md),
  [`.agents/skills/narrativetrace-feedback/`](../.agents/skills/narrativetrace-feedback/SKILL.md),
  [`.agents/skills/add-narrativetrace-clarity/`](../.agents/skills/add-narrativetrace-clarity/SKILL.md),
  [`.agents/skills/narrativetrace-verify/`](../.agents/skills/narrativetrace-verify/SKILL.md) and
  [`.agents/skills/narrativetrace-debug/`](../.agents/skills/narrativetrace-debug/SKILL.md) in
  this repository — Codex's own current skill-discovery documentation (verified 2026-09-14) scans
  `.agents/skills/<name>/SKILL.md` from the working directory up to the repository root, so this
  is the exact path it finds these at, with the same canonical directory names as Claude Code's
  above. The frontmatter carries only `name` and `description` — the two fields Codex documents —
  the page body underneath is byte-identical to Claude Code's.
- **Any agent, any platform**: every agent that reads `AGENTS.md` sees the always-on pointer this
  repository's own `AGENTS.md` carries between its `<!-- narrativetrace:skills:start -->` markers
  — every skill's name and description, so an agent that never thought to look still knows they
  exist.
- **Gemini** has no skill-discovery convention yet — on the roadmap, not built.

## From a registry

A project can carry these skills without anyone here ever running `init`, in one of three states:

1. **Installed by `init`** — committed, the team's. The only state `config.skills-installed`
   passes: the pages carry the provenance line and match the release this project resolves.
2. **A personal install from a registry** (a Claude Code plugin cache) — yours only. Invisible to
   the doctor by design: it diagnoses the project, and a personal install reaches no teammate and
   no other agent.
3. **A registry install into the project** (`npx skills add`) — this repository's own rendered
   pages, landed by a registry rather than by `init`, so they carry no provenance line yet.

Trying the skills yourself, without touching the project:

```text
/plugin marketplace add narrativetrace/narrativetrace-python
/plugin install narrativetrace-python@narrativetrace-python
```

then run `uv run narrativetrace init --dry-run`, read the diff, and run it without the flag so
`AGENTS.md` points at them.

Installing into the project from the open-standard registry:

```text
npx skills add narrativetrace/narrativetrace-python
```

then run `uv run narrativetrace init --dry-run`, read the diff, and run it without the flag so
`AGENTS.md` points at them.

A page a registry left behind is never refused just for being there. `init` compares it, byte for
byte but for the line ending, against what it would have rendered itself. One identical to this
release's own page is **adopted** — the plan says so, rather than "replaced", because a person
reading it has to know that nothing of theirs was overwritten. This is the plan's own text,
quoted, never retyped here:

<!-- snippet: packages/narrativetrace-tooling/src/narrativetrace_tooling/init/plan_renderer.py region=adoptedNote -->
```python
ADOPTED = "adopted: identical to this carrier's page, so only the provenance line is added"
"""What the plan and the report say about a page that was already ours in everything but a line."""

```
<!-- /snippet -->

A page that differs — another release, or hand-edited — keeps the ordinary refusal `--force` is
for. `npx skills add` also leaves `.claude/skills/<name>` a symbolic link to the open-standard
page; `init` never writes through a link like that one. A link whose target it would adopt or
already owns is replaced with a real directory holding the right flavour; every other link is
refused, because `--force` covers content, never a link.

And this is the doctor's own fix, quoted the same way, for a project where the pages are there
but carry none of this:

<!-- snippet: packages/narrativetrace-tooling/src/narrativetrace_tooling/doctor/checks/skills_installed.py region=registryMessages -->
```python
_INIT_COMMAND = "uv run narrativetrace init --dry-run"

_READ_THE_DIFF = f"Run `{_INIT_COMMAND}`, read the diff, then run it without the flag."

_FROM_A_REGISTRY = (
    " Pages that are there without our line usually came from a registry (npx skills add, a plugin"
    " or workspace install). A page identical to this release's is adopted, and no --force is"
    " needed."
)
"""What a page with no provenance line most often IS: a registry install of this repository's own
rendered pages (design D5 state 3). Naming the case matters because the obvious reading of "not
ours" is "somebody else's work", which invites a ``--force`` nobody needs."""

```
<!-- /snippet -->

## How they're built

No skill is ever hand-edited.
`packages/narrativetrace-skills-catalogue/src/narrativetrace_skills/catalogue/add_narrative_tracing.py`,
`.../catalogue/narrativetrace_doctor.py`, `.../catalogue/narrativetrace_feedback.py` and
`.../catalogue/add_narrativetrace_clarity.py` are the
sources of truth; `python scripts/skills_render.py --fix` regenerates each skill's
`.claude/skills/<name>/SKILL.md`, its `.agents/skills/` Codex counterpart, this repository's own
`AGENTS.md` section, and `.claude-plugin/marketplace.json` — the listing that makes this
repository a Claude Code plugin marketplace — from them, and `python scripts/skills_render.py
--check` (wired into `uv run poe check`) fails the build the moment any of these drifts from the
typed source. Every code block a rendered page shows is
embedded from real, tested source through the same `<!-- snippet: -->` marker convention this
repository's other docs use — never a hand-typed example. A Tier A lint keeps private
planning-note citations out of every page: rationale sentences ship, the citation naming the note
does not. A second lint guards the one piece of frontmatter whose absence is a feature: a skill
whose steps can make something public — today, `narrativetrace-feedback` — must declare no
`allowed-tools`, because that field pre-approves its listed tools for the turn that loads the
skill, and a reporting skill that pre-approved its own reporting command would stop the harness
asking exactly where asking is the point. The Claude Code page of such a skill has no `allowed-tools`
line at all, rather than an empty one. A third lint holds a skill that promotes an approval
baseline — today, `narrativetrace-verify` and `narrativetrace-debug` — to the same rule, for the
same reason: the promotion runs through `uv run narrativetrace-approve`, and the yes it waits for
is yours.

## Evaluating them

`packages/narrativetrace-skills-catalogue/evals/` carries the Tier B suite (trigger phrasings, a
happy-path case per skill, a deviation case for the doctor's redaction check; the clarity skill's
happy path starts from a fixture whose unclear names the gate flags and is graded on the gate
running clean afterwards) — never run by
`poe check`; the owner runs it by hand or from the nightly job, through subscription CLIs, never
the metered API. See [its own README](../packages/narrativetrace-skills-catalogue/evals/README.md)
for the sporadic-lane policy (Codex/Gemini) and the promotion matrix.

## See also

- [`narrativetrace-skills-catalogue`](../packages/narrativetrace-skills-catalogue/README.md) — the
  typed catalogue package
- [Sixty Seconds](sixty-seconds.md) — the install-and-first-trace walkthrough
  `add-narrative-tracing`'s steps are drawn from
- [What to Commit](what-to-commit.md) — the approval-trace state the doctor's fourth step checks
- [Privacy and redaction](privacy-and-redaction.md) — the deny-list and value shapes the problem
  report's own value-free rules are measured against
