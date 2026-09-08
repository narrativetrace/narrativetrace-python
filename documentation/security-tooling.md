# Security tooling

Supply-chain and static-analysis scanning for the repository itself — secrets, insecure code
patterns, and known-vulnerable dependencies. This is a different concern from
[`documentation/security-testing.md`](security-testing.md), which fuzzes NarrativeTrace's own
readers/renderers against hostile *input*; this document covers scanning the *codebase and its
dependencies*.

Every tool here has a named `poe` entry point — the CI YAML only ever invokes the task, never a
raw tool command with flags or a pinned version. Tools degrade gracefully when missing locally
(warn-and-pass, the same convention the pre-commit gate already uses for
ruff), and nothing network-dependent runs in a per-commit gate.

## What runs when

| Tool | Entry point | Cadence | Why |
|---|---|---|---|
| gitleaks (staged diff) | `poe secrets-scan-staged` | pre-commit hook, every commit | offline (local git index only); warns and passes if gitleaks isn't installed |
| gitleaks (full history) | `poe secrets-scan` | on-demand only, not wired to CI | network to auto-fetch the binary on first use; see below |
| Bandit | `poe bandit` | `poe check`, every commit | fast, offline, pure Python |
| Semgrep | `poe semgrep` | CI: merge request + scheduled/web | OSS community rulesets only (`p/security-audit`, `p/secrets`) — no `semgrep login`, no custom rules |
| OSV-Scanner | `poe osv-scan` | CI: scheduled/web only, never MR | needs network; MR pipelines re-run per push, which would make it network-dependent per-commit |
| pip-audit | `poe pip-audit` | CI: scheduled/web only, beside OSV-Scanner | overlaps OSV-Scanner by design — both kept cheap, redundancy is the point |

`poe check` (the single per-commit gate) therefore only grew one line: `bandit`. Everything else
that needs the network or is otherwise too slow for every commit follows the same pattern already
established by `poe mutate-gate`/`poe fuzz`/`poe stress` — a separate `poe` task, a separate CI
job, gated by `rules:` to schedule/web (see this repository's private CI config).

## Dependency groups

`bandit` is a normal `dev`-group dependency (`uv sync --all-packages` always installs it, since
`poe check` always needs it). `semgrep` and `pip-audit` live in a separate `security` dependency
group — not installed by a plain `uv sync`, so the default developer sync and the `build` CI job
stay fast. The CI jobs that need them run `uv sync --all-packages --group security` explicitly.

gitleaks and OSV-Scanner have no PyPI package (both are Go binaries) — see below.

## gitleaks and OSV-Scanner: no wheel, so `scripts/run_security_tool.py`

Neither tool ships on PyPI. `poe secrets-scan` and `poe osv-scan` both go through
`scripts/run_security_tool.py`, which:

1. Looks for the tool on `PATH`.
2. Falls back to `.tools/bin/<tool>` (gitignored, cached across runs).
3. Otherwise downloads a **pinned version's** release asset over HTTPS, verifies it against that
   release's **published SHA-256** before ever executing it, extracts it if needed, and caches it
   in `.tools/bin/`.
4. If none of that works (offline, unsupported platform, checksum mismatch) — prints a warning to
   stderr, records `skipped: <reason>` under `build/reports/security-scans/<tool>.status`, and
   exits 0 **locally**. In CI (`CI` set), or under `NARRATIVETRACE_SECURITY_REQUIRED=true`, the
   same missing binary exits 1 instead — see
   [A skipped scan is not a clean scan](#a-skipped-scan-is-not-a-clean-scan) below. The caller
   sees "tool absent", not "tool broken."

Bumping a pinned version means replacing both the URL and the checksum together, copied from that
release's own checksums file (`gitleaks_<version>_checksums.txt` /
`osv-scanner_<version>_SHA256SUMS`) — never typed by hand.

This is why `poe secrets-scan` (full-history) is on-demand only rather than wired into CI: the
brief that added this tooling scoped gitleaks to a pre-commit hook (staged diff, offline, every
commit) plus a full-scan entry point run on request — not a scheduled CI job. **Gap, flagged
deliberately:** unlike Semgrep/OSV-Scanner/pip-audit, nothing currently re-runs the full-history
gitleaks sweep on a schedule. A maintainer who wants that coverage can add a `secrets-scan` job to
the `security` stage mirroring the `osv-scan` job above (`uv sync --all-packages` +
`uv run poe secrets-scan`, `rules: schedule/web`) — it's already offline-safe once cached, so it
would not need the network exception OSV-Scanner and pip-audit need.

## The pre-commit hook

The pre-commit hook runs `gitleaks protect --staged` before its existing format/lint steps,
independent of file type (a leaked key in a `.env` or `.yaml` file matters as much as one in
`.py`). It looks for `gitleaks` on `PATH` or in `.tools/bin/` **only** — it never attempts to
download it, because this hook runs on every commit and per-commit gates never touch the network.
A missing gitleaks warns and passes, exactly like a missing `ruff`; a real finding blocks the
commit (bypass deliberately with `git commit --no-verify`). This hook keeps that graceful-skip
convention deliberately — the hardening below applies only to `scripts/run_security_tool.py`'s
on-demand/scheduled entry points, not to a per-commit gate that must never touch the network.

## A skipped scan is not a clean scan

A scanner whose binary can't be resolved used to warn and pass unconditionally — a green build
that looked like "secrets/dependency scanning passed" when nothing was checked. This is the exact
failure class release-retrospective rule 2 pins ("a graceful-skip tool must prove it has ever
run"), and the one a 2026-09-08 adversarial audit found in the Java spec repo's own Gradle
scanner tasks. Since 2026-09-08, `scripts/run_security_tool.py` (both
`poe secrets-scan` and `poe osv-scan`) behaves as follows when its binary is missing:

- **Locally**: the task **warns** ("a skipped scan is NOT a clean scan") and still exits 0, so a
  machine without the tools keeps a working `check`/pre-commit.
- **In CI (`CI` set), or under `NARRATIVETRACE_SECURITY_REQUIRED=true`**: the task **fails**
  (exit 1) — a run meant to provide security assurance must mean the scan actually ran.
- Every outcome is recorded under `build/reports/security-scans/<tool>.status` as `ran-clean` or
  `skipped: <reason>` (no file at all reads back as `never-ran`), so "ran clean" and "never ran"
  stay distinguishable after the fact, by humans and by jobs alike.

The decision logic lives in `scripts/run_security_tool.py`'s `decide_missing_binary`/
`security_scanners_required`/`record_skipped`/`record_ran_clean`/`scan_status`, unit-tested in
`packages/narrativetrace/tests/test_run_security_tool.py`.

## Bandit: what's skipped and why

`[tool.bandit]` in `pyproject.toml` skips three checks repo-wide, each with its reasoning inline:

- **B101** (`assert_used`) — house style two ways over: pytest tests use bare `assert`
  throughout, and production code asserts postconditions at every function exit
  (the Contract-Augmented TDD convention). Neither is accidental
  control flow that `-O` would silently remove.
- **B105** (`hardcoded_password_string`) — this is a redaction library. Every hit was a
  `"password"`/`"token"`/`"secret"`-named literal used as test fixture or glossary data for the
  redaction feature itself (e.g. `test_rendering.py::test_key_name_redaction`), not a real
  credential.
- **B404** (`import subprocess`) — every actual `subprocess.run` call site is reviewed and
  justified individually (see below); the bare import carries no separate signal once each call
  site is.

Four `subprocess.run` call sites (three pre-existing, one new in `run_security_tool.py`) carry a
targeted inline `# nosec B603, B607 - <reason>` instead of a blanket skip, since unlike the three
skips above, an *unreviewed* future `subprocess.run` elsewhere in the repo should still be
flagged. **Two bandit quirks worth knowing** (both verified empirically against 1.9.4, source:
`bandit/core/manager.py`'s `NOSEC_COMMENT`/`NOSEC_COMMENT_TESTS` regexes):

1. Multiple test IDs in one `# nosec` comment must be separated by `", "` (comma **and** space)
   — `# nosec B603,B607` (no space) only suppresses the first ID listed; the second is silently
   ignored.
2. `NOSEC_COMMENT` captures *everything* after `nosec` up to the next `#` (or end of line) as the
   candidate test-ID list, then tokenizes it on every word — so a human-readable reason appended
   directly (`# nosec B603, B607 - fixed argv, no shell` ) makes bandit log a
   `WARNING Test in comment: fixed is not a test name or id, ignoring` for every word in the
   reason. A second `#` closes the ID list before the prose starts —
   `# nosec B603, B607 # fixed argv, no shell, no untrusted input` — and the warnings disappear.
   Every inline `# nosec` in this repo uses that two-`#` form.

## Semgrep and Bandit false positives

Both tools triage the same way: real findings get fixed (or ledgered with evidence if deferred);
noise gets a targeted, one-line-justified ignore. As of this writing there is exactly one, in
`run_security_tool.py`'s HTTPS download: Semgrep's `dynamic-urllib-use-detected` flags
`urllib.request.urlopen(asset.url, ...)` because `asset.url` isn't a string literal at the call
site. The real risk the rule guards — a `file://`-scheme URL reading arbitrary local files — is
closed by an explicit `if not asset.url.startswith("https://"): raise ValueError(...)` guard
immediately above the call; `asset.url` itself only ever comes from the hardcoded `TOOLS` table,
never external input. Semgrep's rule is purely syntactic and can't see the guard, so the residual
flag is suppressed inline (`# nosemgrep`) with that reasoning attached.

## Running everything locally

```bash
uv run poe bandit               # in-gate, part of poe check
uv run poe secrets-scan-staged  # what the pre-commit hook runs (needs gitleaks on PATH)
uv run poe secrets-scan         # full-history sweep, on demand
uv sync --all-packages --group security
uv run poe semgrep              # OSS community rulesets
uv run poe osv-scan             # lockfile/manifest vulnerability scan
uv run poe pip-audit            # installed-environment vulnerability scan
```
