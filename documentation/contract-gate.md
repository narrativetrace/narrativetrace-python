# The contract gate

`documentation/contract.yaml` is a machine-readable list of claims this repository's
documentation makes — a default, an entry point, a config shape, or the effect a documented shape
produces. `contract-probe/` proves or disproves each one against a **published** install (PyPI,
never this workspace, never `--find-links`), so a doc page and the package someone actually `uv
add`ed can never quietly disagree without a gate noticing.

This is the third leg of the docs-vs-published family, alongside the
`*(since X.Y.Z[, unreleased])*` markers inline in prose and the generated banner under
[`llms.txt`](llms.txt)'s own H1 — see those markers throughout `documentation/*.md` for the
disclosure half of the same problem. This page is the enforcement half: a marker says "this is
new"; the contract gate says "and it is really true of what shipped."

## What it catches

Four kinds of claim, each checked a different way:

| `kind` | What it proves | Example |
|---|---|---|
| `entry-point` | A PyPI project resolves at all, at the version under test | `narrativetrace` |
| `reflectable-default` | The published distribution's own metadata already says what the docs claim — no code runs | `narrativetrace-structlog`'s `Requires-Dist` includes `structlog` unconditionally |
| `probed-default` | A default only visible at runtime (a config-resolution default, a plugin-gated behavior) | `NARRATIVETRACE_APPROVAL` defaults to `false` |
| `config-shape` | A documented configuration shape produces the effect the docs claim | `export_to_logger(trace)` actually emits log records |

Each entry also carries `since`: the version the claim first holds. An entry whose `since` is
**later than the version actually installed** that run is reported `not-applicable-before-since`
— never `fails` — so a documented default for a feature that has not shipped yet does not fail
the gate before its own release does. The exemption is keyed on the version genuinely installed,
never on this repository's own `pyproject.toml` version, which this project keeps at the last
published number until a release tag bumps it (see the `*(since X.Y.Z, unreleased)*` markers
already on many pages).

## Two gates, two cadences

- **`uv run poe contract-lint`** — part of `poe check`, every commit, no network. Validates
  `documentation/contract.yaml` itself: the schema parses, every `since` is a real version string,
  no two entries make the same claim, every entry's `probe` file exists, every `page#anchor`
  pointer resolves to a heading that actually exists on that page, and every
  `*(since X.Y.Z, unreleased)*` marker anywhere in the English docs has at least one contract
  entry recording that version — the mechanical link between the inline markers and this file.
- **`python -m scripts.contract_check`** — nightly, registry-backed, never per commit (the same
  "no network in the per-commit gate" rule `security-tooling.md` describes for the scanners).
  Resolves the version to check the way `scripts/verify_publication_registry.py`'s own lookup
  works (the newest reachable `v*` git tag, else PyPI's own JSON "latest" for `narrativetrace`),
  installs every publishable package at that version into a **fresh temporary environment** — an
  isolated `uv` cache directory, never this checkout's own `.venv`, never an editable workspace
  install standing in for the real registry answer — and runs `contract-probe/`'s runner against
  it. Exits non-zero on any `fails`.

Run the nightly gate by hand against a specific version:

```bash
python -m scripts.contract_check 0.1.1
python -m scripts.contract_check            # omit the version: checks the last published one
python -m scripts.contract_check --dry-run
```

A failure names all four facts in one line, so a skim is enough:

```
documentation/contract.yaml: probed-pytest-artifacts-default documented default "true"
(since 0.1.2) but narrativetrace-pytest 0.1.2 (published) reads "false"
```

## `contract-probe/`

A small, **standalone** `uv` project — its own `pyproject.toml`, its own lockfile, its own
virtual environment — deliberately not a member of this repository's own workspace (`[tool.uv.
workspace].members` in the root `pyproject.toml` globs `packages/*` only). That separation is the
point: every package it proves a claim about is installed at invocation time via `uv run --with
<name>==<version> ...`, resolved from PyPI's default index, never from a `file:` path or this
workspace's own editable install — so what it proves is true of what a consumer would actually
`pip install`, never of this checkout's own working tree. It ships in the public snapshot (not
excluded by `.publishignore`): it is real code proving a documented claim, not private
verification machinery.

Run it directly (mirrors what `scripts/contract_check.py` does for you, one version at a time):

```bash
cd contract-probe
uv run --with narrativetrace==0.1.1 --with narrativetrace-pytest==0.1.1 ... \
    python -m contract_probe.runner --version=0.1.1 \
    --contract=../documentation/contract.yaml --out=contract-result.json
```

Each contract entry dispatches to one probe module under
`contract-probe/src/contract_probe/probes/` — the entry's `probe` field names it, and
`contract-lint` fails if that file does not exist. A probe's `observe()` function returns one
observed string; the entry holds when it equals `documented_default` (or `expected_effect`, the
name the design note uses for a `config-shape` entry — both land in the same field).

A probe module's own imports of `narrativetrace` symbols that do not exist yet at an older
installed version are deferred into `observe()` itself, never left at module level: `contract_
probe.runner` imports every probe module regardless of whether its entry is applicable at the
version under test, so a module-level import of a not-yet-published symbol would break every
OTHER probe's import too, not just its own (see `export_to_logger_probe.py` for the pattern).

## Adding an entry

`contract.yaml` is updated **in the same commit** as the feature that ships a new documented
default — the same discipline the Pro repository's `pro/schema/*.json` files follow. Adding one:

1. Write the sentence in the doc page first, with its `*(since X.Y.Z, unreleased)*` marker if the
   version has not tagged yet.
2. Add the entry to `documentation/contract.yaml`: `id`, `kind`, `page` (the doc path and the
   anchor of the heading carrying the sentence), `claim`, `since`,
   `documented_default`/`expected_effect`, and `probe`.
3. Write the probe module under `contract-probe/src/contract_probe/probes/...`. Use only stable
   public API that already exists at the OLDEST version the contract still checks, or defer the
   import into `observe()` when the claim is precisely about a symbol that does not exist yet —
   `contract-probe` imports every probe module together regardless of which single version is
   under test, so a bare, module-level import of an API that only exists in a newer release
   breaks every other entry's import too.
4. `uv run poe contract-lint` — confirms the shape, the anchor and the since-marker link.
5. `cd contract-probe && uv run --with <name>==<last-published> ... python -m
   contract_probe.runner --version=<last-published>` — confirms the new entry reports
   `not-applicable-before-since` against today's published version (it should, if the feature has
   not released yet) and, once released, reports `holds` against the version it landed in.

## What this deliberately does not cover

- **Prose accuracy outside `contract.yaml`.** A documented explanation that is simply wrong,
  incomplete, or confusing is a different failure mode — review catches that, not a runtime probe.
- **Anything the [Sixty Seconds](sixty-seconds.md) tutorial's own docs-as-tests machinery already
  owns** (`scripts/snippet_check.py`) — `contract.yaml` is for defaults and shapes documented
  elsewhere, not a second copy of that page's own embedded, verified output.
- **Full behavioral equivalence of a complex config object** — one named, checkable
  `expected_effect` per `config-shape` entry, never a spec of the whole feature the shape
  configures.
- **A marker correctly flagged `unreleased` for a version genuinely ahead of the one installed** —
  that is disclosure's job (the inline marker and the generated `llms.txt` banner), not this
  gate's; a `since` later than the installed version is skipped, on purpose, every time.

## See also

- [Duplication Detection](duplication.md) — the other ratchet-style gate this repository runs the
  same way: a report every commit, an enforcement task wired into `poe check`.
- [Security Tooling](security-tooling.md) — the per-commit/nightly split this gate follows for the
  same reason (network calls do not belong in a gate every commit waits on).
- [Sixty Seconds](sixty-seconds.md) — the tutorial project the registry-install technique above is
  written in the same spirit as, once that page's own cold walk needs one.
