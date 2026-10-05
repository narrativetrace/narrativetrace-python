# narrativetrace-skills

The published skills carrier: rendered agent-skill pages (`skills/claude/<name>/SKILL.md`,
`skills/agents/<name>/SKILL.md`) and `skills/catalogue.json` for narrativetrace's free skills.
Resources only — no Python API, nothing to import. `narrativetrace` bundles a byte-identical copy
of the same tree as package data so `init` works without this distribution installed; when this
distribution *is* present in a project, `init` prefers its copy at the project's own resolved
version.

Licensed Apache License, Version 2.0 — unlike every other `narrativetrace*` distribution, which is
BUSL-1.1 (see the root `NOTICE`). This mirrors the Java port's own module split exactly:
`narrativetrace-skills` is `open` (Apache-2.0) in `licensing.properties`, while the typed catalogue
that renders it, [`narrativetrace-skills-catalogue`](../narrativetrace-skills-catalogue), stays
unpublished and BUSL-1.1 like the runtime.

Built entirely as generated output of `narrativetrace-skills-catalogue`'s render step — never
hand-edited. See that package's `README.md` for where the source of truth lives.
