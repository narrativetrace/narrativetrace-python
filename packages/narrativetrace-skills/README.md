# narrativetrace-skills

Typed catalogue source for [narrativetrace](../narrativetrace)'s agent skills *(since 0.1.2)* — the single source of truth `.claude/skills/{doctor,add}/SKILL.md` and this
repository's own `AGENTS.md` managed section are generated from, never hand-edited.

* `narrativetrace_skills.SKILLS` — the two free skills (`narrativetrace-doctor`,
  `add-narrative-tracing`) as typed `Skill` dataclasses: steps, `verify` commands, failure notes,
  always/never rules.
* `narrativetrace_skills.render` — pure functions turning a `Skill` into a rendered `SKILL.md` page
  or the `AGENTS.md` snippet.
* `narrativetrace_skills.lints` — Tier A lints: description budget, closed command vocabulary,
  no private-planning-note citations, Pro-listing status agreement with the feature guide.
* `narrativetrace_skills.replay` — Tier A2 oracle replay: mechanically executes a skill's own step
  data against its fixture, no LLM.

See `documentation/agent-skills.md` for what the two skills do and how they're built, and
`packages/narrativetrace-skills/evals/README.md` for the Tier B (LLM trial) suite.
