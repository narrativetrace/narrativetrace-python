# narrativetrace-skills

The published skills carrier: rendered agent-skill pages (`skills/claude/<name>/SKILL.md`,
`skills/agents/<name>/SKILL.md`) and `skills/catalogue.json` for narrativetrace's free skills.
Resources only — no Python API, nothing to import. `narrativetrace` bundles a byte-identical copy
of the same tree as package data so `init` works without this distribution installed; when this
distribution *is* present in a project, `init` prefers its copy at the project's own resolved
version.

Licensed Apache License, Version 2.0 — unlike the runtime distributions, which are BUSL-1.1 (see
the root `NOTICE`). The `narrativetrace` distribution bundles a copy of these pages and declares
both licences; the pages in it stay Apache-2.0. The typed catalogue that renders them,
[`narrativetrace-skills-catalogue`](../narrativetrace-skills-catalogue), stays unpublished and
BUSL-1.1 like the runtime.

Built entirely as generated output of `narrativetrace-skills-catalogue`'s render step — never
hand-edited. See that package's `README.md` for where the source of truth lives.
