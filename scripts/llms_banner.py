# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Generates and checks the "docs vs published" banner line under `documentation/llms.txt`'s H1
(family design note: `docs-vs-published-gate-2026-09-12.md`, part (a)).

The line states, in one sentence, whether the docs an agent is about to read describe behaviour
that PyPI actually ships yet:

- versions equal:  ``*(Docs and published both at 0.1.1.)*``
- versions differ: ``*(These docs describe 0.1.2; published is 0.1.1.)*``
- offline (no cache hit, no network):
  ``*(These docs describe 0.1.2; published: unknown offline.)*`` — never a guess, never a stale
  cached value presented as current.

**The line also counts `unreleased` since-markers** (owner ruling, 2026-09-12; design note
`docs-vs-published-gate-2026-09-12.md` §1.1 item 8 + §5.1): the repo version stays at the last
*published* number until a release tags it, so the three shapes above can read as fully in sync
while `*(since X.Y.Z, unreleased)*` markers still sit on the page describing behaviour PyPI does
not ship yet. Whenever that count is greater than zero, each shape appends a clause before its
closing period:

- equal:  ``*(Docs and published both at 0.1.3; 4 behaviours marked unreleased.)*``
- differ: ``*(These docs describe 0.1.3; published is 0.1.1; 4 behaviours marked unreleased.)*``
- offline: ``*(These docs describe 0.1.3; published: unknown offline; 4 behaviours marked
  unreleased.)*``
- count zero: the line is unchanged from the three shapes above — no clause at all.

"behaviour" is singular when the count is exactly 1. The count is a pure, deterministic file scan
(:func:`count_unreleased_markers`: `documentation/**` + `README.md` + `llms.txt`/`llms-full.md`,
translated mirrors excluded via the same set `scripts/translation_check.py#translated_files`
already computes), so `check_banner` verifies it on every commit alongside the repo-version half —
unlike the published-version half, which keeps its fresh-cache-only rule (see below).

The repo version comes from the same place `scripts/publish-public.sh#detect_version` reads it
(root `pyproject.toml#version`); the published version is looked up on PyPI via
`scripts.verify_publication_registry`'s own project-level URL and "no answer" sentinel, so this
module never invents a second way to talk to the registry. A successful lookup is cached for up to
`CACHE_TTL_SECONDS` next to the build output (`build/`, already git-ignored) so repeated local
builds within the hour don't hammer PyPI; a cache hit's age is folded into a trailing HTML comment
(invisible on GitHub and in the site's doc viewer) rather than presented silently as fresh.

Wired into the same two build steps as the snippet-check/-sync machinery: `sync_banner` (called
from `snippet_sync.py`, a developer/CI action never wired into `poe check`) does the live PyPI
lookup and writes the current line. `check_banner` (called from `snippet_check.py`, which IS wired
into `poe check` — the per-commit foreground gate) never touches the network itself, matching that
module's existing "no network, reads files only" contract and this repo's thin-CI convention
(network-backed checks are nightly, never per-commit — see `documentation/security-tooling.md`'s
own split): it always verifies the banner's *repo*-version token against `pyproject.toml` (free,
deterministic, catches the "bumped the version, forgot to rerun snippet-sync" defect on its own),
and opportunistically verifies the *published*-version half too, but only when a still-fresh cache
already sits on disk from an earlier `sync_banner` run — never by dialing out on its own, and never
by failing the build merely because this run happens to be offline (the design note's own example
of the standing offline case: the 02:00 nightly job on this machine).
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from scripts.translation_check import REPO_ROOT, translated_files
from scripts.verify_publication_registry import DEFAULT_REGISTRY_BASE, project_url

PACKAGE_NAME = "narrativetrace"  # the core package: the one every install starts with
LLMS_TXT_RELATIVE = "documentation/llms.txt"
CACHE_RELATIVE = "build/llms-banner-cache.json"
CACHE_TTL_SECONDS = 3600.0

_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
_BANNER_LINE_RE = re.compile(r"^\*\(.*\)\*(?:\s*<!--.*-->)?\s*$")
_UNRELEASED_MARKER_RE = re.compile(r"\*\(since\s+[0-9]+(?:\.[0-9]+)*,\s*unreleased\)\*")
_UNRELEASED_CLAUSE_RE = re.compile(r"; (\d+) behaviours? marked unreleased")


def read_repo_version(repo_root: Path) -> str:
    """The repo's own version, read the way `scripts/publish-public.sh#detect_version` does:
    the first `version = "..."` line in the root `pyproject.toml`."""
    text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    match = _VERSION_RE.search(text)
    if match is None:
        raise ValueError("pyproject.toml: no top-level 'version = \"...\"' line found")
    return match.group(1)


def fetch_latest_version(name: str, *, registry_base: str = DEFAULT_REGISTRY_BASE) -> str | None:
    """The latest version PyPI serves for `name`, or `None` for "no answer" (the same `0`/404-style
    sentinel `verify_publication_registry` already uses) — never raises on a network failure."""
    url = project_url(registry_base, name)
    try:
        with urllib.request.urlopen(  # nosec B310 - registry_base is DEFAULT_REGISTRY_BASE unless
            # a caller deliberately overrides it (e.g. a rehearsal against TestPyPI).
            url,
            timeout=15.0,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None
    version = payload.get("info", {}).get("version")
    return version if isinstance(version, str) and version else None


def _read_cache(cache_path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_cache(cache_path: Path, *, version: str, timestamp: float) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"package": PACKAGE_NAME, "version": version, "timestamp": timestamp}),
        encoding="utf-8",
    )


def _read_fresh_cache(
    repo_root: Path, *, now: float | None, ttl_seconds: float
) -> tuple[str, float] | None:
    """`(version, age_seconds)` from the on-disk cache if it exists, names `PACKAGE_NAME`, and is
    within `ttl_seconds` — `None` otherwise. Never touches the network."""
    clock = time.time if now is None else (lambda: now)
    cached = _read_cache(repo_root / CACHE_RELATIVE)
    if cached is None or cached.get("package") != PACKAGE_NAME:
        return None
    timestamp = cached.get("timestamp", 0.0)
    age = clock() - float(timestamp) if isinstance(timestamp, (int, float)) else float("inf")
    version = cached.get("version")
    if 0 <= age < ttl_seconds and isinstance(version, str):
        return version, age
    return None


def get_published_version(
    repo_root: Path,
    *,
    now: float | None = None,
    fetch: Callable[[str], str | None] = fetch_latest_version,
    ttl_seconds: float = CACHE_TTL_SECONDS,
    allow_network: bool = True,
) -> tuple[str | None, float | None]:
    """`(version, cache_age_seconds)` for `PACKAGE_NAME` on PyPI.

    `cache_age_seconds` is `0.0` for a fresh live lookup, the cache's age in seconds for a lookup
    served from the (still-fresh) on-disk cache, and `None` alongside a `None` version for the
    offline case: no fresh cache, and either `allow_network` is `False` (the per-commit
    `check_banner` path — see module docstring) or the live lookup came back with no answer. A
    stale (past-TTL) cache is never handed back as if it were current — that would be exactly the
    "guess" the banner line promises never to make.
    """
    cached = _read_fresh_cache(repo_root, now=now, ttl_seconds=ttl_seconds)
    if cached is not None:
        return cached
    if not allow_network:
        return None, None
    clock = time.time if now is None else (lambda: now)
    fetched = fetch(PACKAGE_NAME)
    if fetched is not None:
        _write_cache(repo_root / CACHE_RELATIVE, version=fetched, timestamp=clock())
        return fetched, 0.0
    return None, None


def _unreleased_marker_files(repo_root: Path) -> list[Path]:
    """Every English doc file the `unreleased` count is read from: every `*.md` file under
    `documentation/` plus `documentation/llms.txt` (mirrors `scripts/snippet_check.py`'s own
    "English pages" definition, kept independent here rather than imported — `snippet_check`
    already imports `check_banner` from this module, so importing back would cycle), plus the
    root `README.md`. Translated mirrors are excluded via the same
    `scripts.translation_check.translated_files` set `snippet_check` uses."""
    translated = {path.resolve() for path in translated_files(repo_root)}
    documentation = repo_root / "documentation"
    files: list[Path] = []
    if documentation.is_dir():
        files.extend(
            path for path in sorted(documentation.rglob("*.md")) if path.resolve() not in translated
        )
        llms_txt = documentation / "llms.txt"
        if llms_txt.is_file() and llms_txt.resolve() not in translated:
            files.append(llms_txt)
    readme = repo_root / "README.md"
    if readme.is_file() and readme.resolve() not in translated:
        files.append(readme)
    return files


def count_unreleased_markers(repo_root: Path) -> int:
    """How many `unreleased` since-markers (each a `*(since X.Y.Z, unreleased)*` clause) sit
    across the English docs right now. A pure, deterministic file scan — no network, no clock —
    so `check_banner` can verify it on every commit (see module docstring)."""
    total = 0
    for path in _unreleased_marker_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        total += len(_UNRELEASED_MARKER_RE.findall(text))
    return total


def _unreleased_clause(count: int) -> str:
    """The `; N behaviour(s) marked unreleased` clause `render_banner` inserts before the closing
    period — empty for a count of zero, so the line reads exactly as it did before this feature."""
    if count <= 0:
        return ""
    noun = "behaviour" if count == 1 else "behaviours"
    return f"; {count} {noun} marked unreleased"


def _extract_unreleased_count(line: str) -> int:
    """The count a banner line's clause currently states, or ``0`` when it carries none at all —
    the two are equivalent renderings of "nothing unreleased right now"."""
    match = _UNRELEASED_CLAUSE_RE.search(line)
    return int(match.group(1)) if match else 0


def _format_age(age_seconds: float) -> str:
    minutes = int(age_seconds // 60)
    if minutes < 1:
        return "under a minute"
    if minutes == 1:
        return "1m"
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    return f"{hours}h{minutes % 60:02d}m"


def render_banner(
    repo_version: str,
    published_version: str | None,
    cache_age: float | None,
    unreleased_count: int = 0,
) -> str:
    """The banner line's exact text, per the design note's three cases, each optionally carrying
    the `; N behaviour(s) marked unreleased` clause (see module docstring) when
    `unreleased_count` is greater than zero."""
    clause = _unreleased_clause(unreleased_count)
    if published_version is None:
        return f"*(These docs describe {repo_version}; published: unknown offline{clause}.)*"
    if published_version == repo_version:
        core = f"*(Docs and published both at {repo_version}{clause}.)*"
    else:
        core = f"*(These docs describe {repo_version}; published is {published_version}{clause}.)*"
    if cache_age and cache_age > 0:
        core = f"{core} <!-- registry checked {_format_age(cache_age)} ago -->"
    return core


def _strip_cache_comment(line: str) -> str:
    return re.sub(r"\s*<!--.*-->\s*$", "", line).strip()


def compute_banner_line(
    repo_root: Path, *, allow_network: bool = True, now: float | None = None
) -> str:
    repo_version = read_repo_version(repo_root)
    published_version, cache_age = get_published_version(
        repo_root, allow_network=allow_network, now=now
    )
    unreleased_count = count_unreleased_markers(repo_root)
    return render_banner(repo_version, published_version, cache_age, unreleased_count)


_REPO_VERSION_TOKEN_RE = re.compile(
    r"^\*\((?:Docs and published both at|These docs describe)\s+([0-9]+(?:\.[0-9]+)*)"
)


def _extract_repo_version_token(line: str) -> str | None:
    """The repo-version half of a banner line — checkable with no network at all, so this is the
    one thing `check_banner` always verifies regardless of registry reachability."""
    match = _REPO_VERSION_TOKEN_RE.match(line.strip())
    return match.group(1) if match else None


def _find_banner_line_index(lines: list[str]) -> int | None:
    """The index of the existing banner line (immediately following the H1, allowing one blank
    line between them), or `None` if `llms.txt` doesn't have one yet."""
    for i, line in enumerate(lines):
        if line.startswith("# "):
            j = i + 1
            if j < len(lines) and lines[j].strip() == "":
                j += 1
            if j < len(lines) and _BANNER_LINE_RE.match(lines[j].strip()):
                return j
            return None
    return None


def sync_banner(repo_root: Path) -> str | None:
    """Writes the current banner line into `documentation/llms.txt`, right after its H1 (with one
    blank line between, matching the file's existing style). Returns a change description when the
    *content* changed (ignoring a cache-age comment refresh), `None` otherwise."""
    path = repo_root / LLMS_TXT_RELATIVE
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    new_line = compute_banner_line(repo_root)
    existing_index = _find_banner_line_index(lines)
    if existing_index is not None:
        old_line = lines[existing_index]
        if old_line == new_line:
            return None
        lines[existing_index] = new_line
        content_changed = _strip_cache_comment(old_line) != _strip_cache_comment(new_line)
    else:
        h1_index = next(i for i, line in enumerate(lines) if line.startswith("# "))
        lines[h1_index + 1 : h1_index + 1] = ["", new_line]
        content_changed = True
    path.write_text("\n".join(lines), encoding="utf-8")
    if content_changed:
        return f"{LLMS_TXT_RELATIVE}: banner set to {_strip_cache_comment(new_line)}"
    return None


def check_banner(repo_root: Path) -> list[str]:
    """Every way `documentation/llms.txt`'s banner line is out of date, found without ever touching
    the network (see module docstring):

    1. The line must exist, right under the H1, in one of the two/three recognised shapes.
    2. Its repo-version token must match `pyproject.toml#version` right now — this alone catches
       the defect class that matters most (a version bump landed and nobody reran
       `poe snippet-sync`), and needs no registry at all.
    3. Its unreleased-count clause must match `count_unreleased_markers` right now — deterministic,
       like the repo-version check, so it is verified every commit regardless of registry
       reachability (see module docstring).
    4. If a still-fresh cache from an earlier `sync_banner` run happens to be on disk, the
       published-version half is checked against it too — a bonus catch, never a requirement: a
       cold or expired cache (the standing case for an offline nightly run) is not a failure.
    """
    path = repo_root / LLMS_TXT_RELATIVE
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").split("\n")
    existing_index = _find_banner_line_index(lines)
    repo_version = read_repo_version(repo_root)
    unreleased_count = count_unreleased_markers(repo_root)
    if existing_index is None:
        expected = _strip_cache_comment(
            render_banner(repo_version, repo_version, None, unreleased_count)
        )
        return [
            f"{LLMS_TXT_RELATIVE}: missing the docs-vs-published banner line under the H1 "
            f"— run 'poe snippet-sync' (e.g. {expected!r})"
        ]
    actual = _strip_cache_comment(lines[existing_index])
    actual_repo_version = _extract_repo_version_token(actual)
    if actual_repo_version != repo_version:
        return [
            f"{LLMS_TXT_RELATIVE}:{existing_index + 1}: docs-vs-published banner names version "
            f"{actual_repo_version!r} but pyproject.toml is at {repo_version!r} — run "
            f"'poe snippet-sync' to refresh it"
        ]
    actual_unreleased_count = _extract_unreleased_count(actual)
    if actual_unreleased_count != unreleased_count:
        return [
            f"{LLMS_TXT_RELATIVE}:{existing_index + 1}: docs-vs-published banner counts "
            f"{actual_unreleased_count} behaviours marked unreleased but the docs currently mark "
            f"{unreleased_count} — run 'poe snippet-sync' to refresh it"
        ]
    cached = _read_fresh_cache(repo_root, now=None, ttl_seconds=CACHE_TTL_SECONDS)
    if cached is not None:
        published_version, cache_age = cached
        expected = _strip_cache_comment(
            render_banner(repo_version, published_version, cache_age, unreleased_count)
        )
        if actual != expected:
            return [
                f"{LLMS_TXT_RELATIVE}:{existing_index + 1}: docs-vs-published banner is stale "
                f"({actual!r}) — run 'poe snippet-sync' to update it to {expected!r}"
            ]
    return []


def main() -> int:
    changed = sync_banner(REPO_ROOT)
    if changed is None:
        print("llms-banner: nothing to do — the docs-vs-published banner already matches")
        return 0
    print(f"llms-banner: {changed}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
