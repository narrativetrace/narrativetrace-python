# Sporadic eval quota

The two cheaper Tier B lanes (Codex, Gemini) run under the sporadic policy in `evals/README.md`:
never scheduled, promotion points only, quota-guarded. `evals/run.py` reads this file before every
codex/gemini trial and refuses to start once the current ISO week's spend reaches the platform's
weekly allowance below — **there is no override flag**; raise the number here instead. The Claude
lane is not sporadic (it runs on the harness's own regular cadence) and carries no quota row.

## Allowance

Mirrors the TypeScript reference's own owner-ruled allowance: Codex is available on the basic plan
at the same default sporadic-lane allowance; Gemini stays at 0 -- refusing every trial -- until the
CLI is installed, signed in, and the owner raises the number.

| platform | plan tier | weekly allowance |
|---|---|---|
| codex | basic | 4 |
| gemini | not installed | 0 |

## Spend log

Appended by the runner (`evals/run.py`), one row per sporadic-lane (codex/gemini) trial —
Claude-lane trials never append here. `week` is the ISO 8601 week (`iso_week()` in `evals/quota.py`)
the trial's own date falls in, so a week boundary crossing mid-run is judged the same way twice.

| date | platform | skill | case | week |
|---|---|---|---|---|
