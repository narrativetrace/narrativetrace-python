# Sporadic eval quota

The cheaper Tier B lanes (Codex, Antigravity, Cursor) run under the sporadic policy in `evals/README.md`:
never scheduled, promotion points only, quota-guarded. `evals/run.py` reads this file before every
codex/antigravity/cursor trial and refuses to start once the current ISO week's spend reaches the platform's
weekly allowance below — **there is no override flag**; raise the number here instead. The Claude
lane is not sporadic (it runs on the harness's own regular cadence) and carries no quota row.

## Allowance

Mirrors the TypeScript reference's own owner-ruled allowance: Codex is available on the basic plan
at the same default sporadic-lane allowance. Antigravity replaced the Gemini CLI lane on 2026-10-10
(owner: "use Antigravity instead of Gemini CLI"); its `agy` CLI is installed and signed in on the
owner's workstation, so it carries the same default allowance as Codex. Cursor (owner item, Phase 8,
platform pointers) stays at 0 -- skipping every trial with one line -- until its `agent` CLI is
installed and signed in.

| platform | plan tier | weekly allowance |
|---|---|---|
| codex | basic | 4 |
| antigravity | subscription | 4 |
| cursor | not installed | 0 |

## Spend log

Appended by the runner (`evals/run.py`), one row per sporadic-lane (codex/antigravity/cursor) trial —
Claude-lane trials never append here. `week` is the ISO 8601 week (`iso_week()` in `evals/quota.py`)
the trial's own date falls in, so a week boundary crossing mid-run is judged the same way twice.

| date | platform | skill | case | week |
|---|---|---|---|---|
