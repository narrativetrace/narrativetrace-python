# Agent skills

*(since 0.1.2, unreleased)*

NarrativeTrace ships **skills**: agent-loadable procedures that run tested commands and gate
completion on a `verify` step, rather than docs an agent might or might not read. A skill is thin
by design — the checking, diagnosis, or generation logic lives in tested library code; the skill's
own job is knowing when to act, invoking that tested code, and interpreting the result in context.

## Two skills: setup and diagnosis

- **`add-narrative-tracing`** — installs NarrativeTrace into a project and gets it to a first
  trace: install with the real toolchain (`uv add narrativetrace`), wrap an object, render and run
  the first trace, then wire a real logger (the stdlib `logging` bridge). Ends by running `uv run
  narrativetrace doctor` and handing off — the seam between the two skills.
- **`narrativetrace-doctor`** — diagnosis only, and **read-only**: it never edits, generates, or
  deletes a file. Runs the tested CLI, reads its report, and walks through the parts a plain CLI
  output can't cover on its own: proving redaction in a test, reading a rendered trace before
  asserting against it, and the approval-trace flow (flagged unstudied — its own eval cell is
  still pending).

They compose: a brand-new project starts with `add-narrative-tracing`; a project that already has
NarrativeTrace installed, where something isn't working, starts with `narrativetrace-doctor`.
Either path ends at the doctor — it owns diagnosis from there. A later skill will own generation
(writing the redaction-proof test the doctor can only ask you to add today).

## The `narrativetrace` CLI

Both skills run `uv run narrativetrace doctor` — the free CLI's `doctor` verb, alongside the
existing `narrativetrace-approve` console script. Read-only, zero network, `--json` for machine
output, exit `0` (clean), `1` (findings), or `2` (could not run). Eleven checks with stable, dotted
ids: interpreter/pytest versions against what's declared, the eight `narrativetrace-*` packages
agreeing on one version, `NARRATIVETRACE_OUTPUT`'s spelling, the pytest plugin's registration,
unrecognized `narrativetrace.toml` keys, an imported-but-unused redaction marker, a `*args`
method's parameters collapsing to one `args: [...]` value, whether redaction is proven in a test,
and stale approval-trace diffs.

## Installing them

- **Claude Code**: rendered `SKILL.md` files live at
  [`.claude/skills/add-narrative-tracing/`](../.claude/skills/add-narrative-tracing/SKILL.md) and
  [`.claude/skills/narrativetrace-doctor/`](../.claude/skills/narrativetrace-doctor/SKILL.md) in
  this repository — the directory name and the frontmatter `name:` are always the catalogue's
  canonical id, never a shortened segment: a repo-level `.claude/skills/` directory is a flat
  namespace, not a Claude Code plugin, so a shortened name (`doctor`) would collide with every other
  vendor's skill of that name. Copy either directory into your own project's
  `.claude/skills/<name>/` and Claude picks it up on its own, invokable by name
  (`add-narrative-tracing` / `narrativetrace-doctor`) directly.
- **Codex CLI**: rendered `SKILL.md` files live at
  [`.agents/skills/add-narrative-tracing/`](../.agents/skills/add-narrative-tracing/SKILL.md) and
  [`.agents/skills/narrativetrace-doctor/`](../.agents/skills/narrativetrace-doctor/SKILL.md) in
  this repository — Codex's own current skill-discovery documentation (verified 2026-09-14) scans
  `.agents/skills/<name>/SKILL.md` from the working directory up to the repository root, so this
  is the exact path it finds these at, with the same canonical directory names as Claude Code's
  above. The frontmatter carries only `name` and `description` — the two fields Codex documents —
  the page body underneath is byte-identical to Claude Code's.
- **Any agent, any platform**: every agent that reads `AGENTS.md` sees the always-on pointer this
  repository's own `AGENTS.md` carries between its `<!-- narrativetrace:skills:start -->` markers
  — both skills' names and descriptions, so an agent that never thought to look still knows they
  exist.
- **Gemini and an automatic installer** are on the roadmap but not built yet — today, copying the
  rendered files is the path for any platform without its own discovery convention.

## How they're built

Neither skill is ever hand-edited.
`packages/narrativetrace-skills/src/narrativetrace_skills/catalogue/add_narrative_tracing.py` and
`.../catalogue/narrativetrace_doctor.py` are the two sources of truth; `python
scripts/skills_render.py --fix` regenerates `.claude/skills/add-narrative-tracing/SKILL.md`,
`.claude/skills/narrativetrace-doctor/SKILL.md`, their `.agents/skills/` Codex counterparts, and
this repository's own `AGENTS.md` section from them, and
`python scripts/skills_render.py --check` (wired into `uv run poe check`) fails the build the
moment any of the five drifts from the typed source. Every code block a rendered page shows is
embedded from real, tested source through the same `<!-- snippet: -->` marker convention this
repository's other docs use — never a hand-typed example. A Tier A lint keeps private
planning-note citations out of both pages: rationale sentences ship, the citation naming the note
does not.

## Evaluating them

`packages/narrativetrace-skills/evals/` carries the Tier B suite (trigger phrasings, a happy-path
case per skill, a deviation case for the doctor's redaction check) — never run by `poe check`; the
owner runs it by hand or from the nightly job, through subscription CLIs, never the metered API.
See [its own README](../packages/narrativetrace-skills/evals/README.md) for the sporadic-lane
policy (Codex/Gemini) and the promotion matrix.

## See also

- [`narrativetrace-skills`](../packages/narrativetrace-skills/README.md) — the typed catalogue
  package
- [Sixty Seconds](sixty-seconds.md) — the install-and-first-trace walkthrough
  `add-narrative-tracing`'s steps are drawn from
- [What to Commit](what-to-commit.md) — the approval-trace state the doctor's fourth step checks
