# Use NarrativeTrace with your agent

NarrativeTrace ships [agent skills](agent-skills.md) — the procedures an agent follows to install the
library, read a trace and diagnose an install — in the open Agent Skills format. Every platform in
the table below already discovers the pages `init` writes under `.agents/skills`, so there is one set
of pages and no per-platform copy. What differs from platform to platform is how a stranger gets the
pages into a project, and which small file points the agent at them before it happens to look.

## Platforms at a glance

<!-- platform-table:begin -->
| Platform | How a stranger gets the skills | What the agent finds after `init` | Evidence | Verified |
|---|---|---|---|---|
| Cursor | Install the plugin from the public repository's `.cursor-plugin` manifest, or run `uv run narrativetrace init` in the project | the skills in `.agents/skills` (Cursor also reads `.claude/skills`), and the one rule `.cursor/rules/narrativetrace.mdc` that points at them | Tier B lane `cursor` | 2026-10-10 |
| Replit | Import the public repository from GitHub (paste its URL, preview the skills, add them), or run `uv run narrativetrace init` in the project | the skills in `.agents/skills`, and a NarrativeTrace section in `replit.md`, the project memory the Replit agent reads first | manual trial | 2026-10-10 |
| Antigravity | Nothing to install beyond the project itself: run `uv run narrativetrace init` in the project and commit the skills (the `agy` CLI and the IDE read them as workspace skills) | the skills in `.agents/skills`, which Antigravity reads as workspace skills, and the section in `AGENTS.md`, which it loads as rules | Tier B lane `antigravity` | 2026-10-10 |
| GitHub Copilot | Nothing to install beyond the repository itself: run `uv run narrativetrace init` in the project and commit the skills | the skills in `.agents/skills` (Copilot also reads `.claude/skills` and `.github/skills`), and the section in `AGENTS.md` | manual trial | 2026-10-10 |
| Claude Code | Add the repository as a plugin marketplace and install its plugin, or run `uv run narrativetrace init` in the project | the skills in `.claude/skills` and `.agents/skills`, and the section in `AGENTS.md` that `CLAUDE.md` imports | Tier B lane `claude` | 2026-10-10 |
<!-- platform-table:end -->

The table is rendered from the platform registry the installer and the doctor read, so it cannot
disagree with what `init` does. The Verified column is the date each row's facts were last checked
against the platform's own documentation; platform behaviour moves quickly, so treat that date as
part of the answer and the vendor's documentation as the authority.

## The pointer files `init` writes

A pointer is one small file the platform already reads first. It is written only when the project
shows the platform is in use, never as a copy of a skill page, and never through a symbolic link:

- **Cursor** — `.cursor/rules/narrativetrace.mdc`, one always-applied rule saying where the skills
  live, written only when the project has a `.cursor/` directory. The Cursor plugin ships the same
  rule.
- **Replit** — a marked NarrativeTrace section in `replit.md`, the project memory the Replit agent
  reads first, written only when the project has `replit.md` or `.replit`. It is the same section
  `AGENTS.md` carries, with the same markers.
- **Antigravity, GitHub Copilot, Claude Code** — no pointer. They read `.agents/skills` and
  `AGENTS.md` directly (Antigravity loads `AGENTS.md` as rules; Claude Code also reads
  `.claude/skills`, which `init` writes on every project).

A pointer that is already identical to what `init` would write is adopted rather than refused, a
file that is not ours is refused without `--force`, and `uv run narrativetrace uninstall` removes
exactly the pointers it wrote. `uv run narrativetrace doctor` reports each detected platform's
pointer as present and current, or names what is missing, stale or foreign.

## Copying by hand

Copying works for any platform, and is the only path for an agent with no `narrativetrace` command
of its own:

- **Codex**: the catalogue renders
  [`.agents/skills/narrativetrace-doctor/`](../.agents/skills/narrativetrace-doctor/SKILL.md) and
  the other skill directories in the same folder — the repo-checked-in layout Codex CLI documents
  for a project's own skills. Its frontmatter carries only `name` and `description` (Codex
  documents no `when_to_use` or `allowed-tools` keys); the page body is otherwise identical. Copy
  the relevant directory into your own project's `.agents/skills/<name>/` and Codex discovers it the
  same way.
- **Antigravity**: workspace skills are read from `.agents/skills/` (legacy `.agent/skills/`), so
  the same copy works in the IDE and in the `agy` CLI. Its plugin installer reads only a plugin's
  top-level `skills/` directory, which this repository does not ship, so there is no
  `agy plugin install` path.
- **Any agent, any platform**: every agent that reads `AGENTS.md` sees the always-on section `init`
  writes there — the skills' names and descriptions, so an agent that never thought to look still
  knows they exist.

## Evidence

Each platform's row names the trial that backs it. The Claude, Codex, Antigravity and Cursor lanes drive
the real command-line agent against the install prompt on a fixture project, and a lane whose CLI
is not installed skips with one line rather than failing; Replit and GitHub Copilot are manual
trials recorded by the owner. The lanes, the sporadic quota policy and the promotion matrix are
described in [Tier B — LLM trials](../packages/narrativetrace-skills-catalogue/evals/README.md).

## Related

- [Agent Skills](agent-skills.md) — what the skills are, how they are built, and the installer
- [Installation Guide](guides/installation.md) — the library itself
