# narrativetrace-skills-catalogue

Typed catalogue source for [narrativetrace](../narrativetrace)'s agent skills — the single
source of truth `.claude/skills/{doctor,add}/SKILL.md`, this repository's own `AGENTS.md` managed
section, the published [`narrativetrace-skills`](../narrativetrace-skills/README.md) carrier
distribution, and `narrativetrace`'s own bundled copy are all generated from, never hand-edited.
Private (`Private :: Do Not Upload`) — never published itself; only the pages it renders are.

* `narrativetrace_skills.SKILLS` — the four free skills (`narrativetrace-doctor`,
  `add-narrative-tracing`, `narrativetrace-feedback`, `add-narrativetrace-clarity`) as typed
  `Skill` dataclasses: steps, `verify` commands, failure notes, always/never rules.
  `narrativetrace-feedback` can publish, so it declares no `allowed_tools`.
* `narrativetrace_skills.render` — pure functions turning a `Skill` into a rendered `SKILL.md` page
  or the `AGENTS.md` snippet.
* `narrativetrace_skills.lints` — Tier A lints: description budget, closed command vocabulary,
  no private-planning-note citations, Pro-listing status agreement with the feature guide, and
  that a skill whose steps can publish pre-approves no tool.
* `narrativetrace_skills.replay` — Tier A2 oracle replay: mechanically executes a skill's own step
  data against its fixture, no LLM.

See `documentation/agent-skills.md` for what the skills do and how they're built, and
`packages/narrativetrace-skills-catalogue/evals/README.md` for the Tier B (LLM trial) suite.
