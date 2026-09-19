# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Post-publish marker settle (`scripts/settle-markers.sh`; docs-vs-published-gate design,
decision 1).

`scripts/publish-public.sh`'s `--tag` step rewrites every doc marker `*(since X, unreleased)*`
whose cited version X equals the release's own version to `*(since X)*` — but only in the STAGED
(published) snapshot, never in-tree (the same "stamped only at publish time" discipline as the
BUSL-1.1 license header). That is correct for the snapshot that ships, but it leaves the PRIVATE
tree carrying the stale `unreleased` form for a version that, the moment the tag publish lands on
the registry, is no longer unreleased at all: the next untagged snapshot push (not a release, just
a working-tree mirror) would ship "unreleased" for a version that is actually live.

This module is the settle step that closes that gap: run once, right after a tag publish, it
applies the identical mechanical rewrite directly to the private working tree, refreshes the
docs-vs-published banner (`documentation/llms.txt`) so its own generated `unreleased`-marker count
matches what survives, and restamps every translated mirror whose named English source's bytes
ended up different from how they started — whether the rewrite or the banner/snippet refresh is
what changed them, so a mirror of a page the refresh alone touched (no marker of its own) is never
left pointing at a stale hash. It refuses to run against a version the registry does not yet
report as published — a settle must never run ahead of the publish it is settling.

Scope, mirrored from `publish-public.sh`'s `--tag` rewrite (`find "$STAGE" -type f \\(-name
'*.md' -o -name 'llms.txt'\\)` over the whole staged snapshot, which by then contains only
`documentation/` and the handful of root files `.publishignore` leaves alone): every `*.md` file
and `llms.txt` under `documentation/`, the root `README.md`, and every translated mirror that
names `README.md` as its own source header (found generically via
`scripts.translation_check.translated_files` — never a hardcoded per-language filename list, so a
fifth language needs no change here). Source and test files are never in scope: a marker-shaped
string there is a fixture, not a doc, the same rule the publish script's own scope draws.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.llms_banner import (
    fetch_latest_version,
    get_published_version,
    sync_banner,
)
from scripts.translation_check import (
    REPO_ROOT,
    git_blob_hash,
    parse_header,
    translated_files,
)


def _marker_pattern(version: str) -> re.Pattern[str]:
    """The exact marker regex `scripts/publish-public.sh`'s `--tag` step matches, functionally
    identical to its `perl -0777` slurp expression: `\\s+`/`\\s*` (which match a real newline the
    same way `perl -0777`'s slurp mode does) tolerate both Markdown hard-wrap shapes a marker can
    survive — right after `since` or right after the version's comma — so a line-based check
    could silently miss a wrapped marker where this does not."""
    return re.compile(rf"since\s+{re.escape(version)},\s*unreleased\)\*")


def _first_line(path: Path) -> str:
    with path.open(encoding="utf-8") as handle:
        return handle.readline().rstrip("\n").rstrip("\r")


def discover_marker_files(repo_root: Path) -> list[Path]:
    """Every file in the settle rewrite's scope — see module docstring."""
    files: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        if path.is_file():
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(path)

    documentation = repo_root / "documentation"
    if documentation.is_dir():
        for path in sorted(documentation.rglob("*.md")):
            add(path)
        add(documentation / "llms.txt")

    add(repo_root / "README.md")

    for path in translated_files(repo_root):
        header = parse_header(_first_line(path))
        if header is not None and header.source_path == "README.md":
            add(path)

    return files


@dataclass(frozen=True)
class SettleResult:
    """What one `settle_version` run did — enough to print the "count settled + files touched"
    report the release procedure requires, and for a test to assert on precisely."""

    marker_count: int
    rewritten_files: list[str] = field(default_factory=list)
    restamped_files: list[str] = field(default_factory=list)


def _restamp_mirrors_of(
    repo_root: Path, mirrors: list[Path], source_rel: str, new_hash: str
) -> list[str]:
    """Restamps the hash portion (never the `translated`/`reviewed` dates a human set) of every
    mirror in `mirrors` that names `source_rel` as its source, to `new_hash` — the source file's
    bytes right after the rewrite that made this call happen. Returns the restamped mirrors'
    repo-relative paths."""
    restamped: list[str] = []
    for mirror in mirrors:
        first_line = _first_line(mirror)
        header = parse_header(first_line)
        if header is None or header.source_path != source_rel:
            continue
        if header.blob_hash_prefix == new_hash:
            continue
        restamped_line = first_line.replace(
            f"source: {source_rel} blob {header.blob_hash_prefix}",
            f"source: {source_rel} blob {new_hash}",
        )
        if restamped_line == first_line:
            continue
        _, _, rest = mirror.read_text(encoding="utf-8").partition("\n")
        mirror.write_text(restamped_line + "\n" + rest, encoding="utf-8")
        restamped.append(mirror.resolve().relative_to(repo_root.resolve()).as_posix())
    return restamped


def _rewrite_markers(
    repo_root: Path, scope: list[Path], pattern: re.Pattern[str], replacement: str
) -> tuple[list[str], int]:
    """Applies `pattern`/`replacement` to every file in `scope`, in place. Returns the repo-relative
    paths actually rewritten and the total marker count across all of them."""
    rewritten: list[str] = []
    total_markers = 0
    for path in scope:
        before = path.read_text(encoding="utf-8")
        after, count = pattern.subn(replacement, before)
        if count == 0:
            continue
        path.write_text(after, encoding="utf-8")
        rewritten.append(path.resolve().relative_to(repo_root.resolve()).as_posix())
        total_markers += count
    return rewritten, total_markers


def _restamp_changed_sources(
    repo_root: Path,
    scope: list[Path],
    mirrors: list[Path],
    before_hashes: dict[Path, str],
) -> list[str]:
    """For every file in `scope` whose current hash no longer matches `before_hashes`, restamps
    every mirror naming it as source. Catches a source changed by *any* step run over `scope`
    since the snapshot — a marker rewrite or a regeneration hook alike — not only files a marker
    rewrite itself touched."""
    restamped: list[str] = []
    for path in scope:
        if not path.is_file():
            continue
        new_hash = git_blob_hash(path.read_bytes())
        if new_hash == before_hashes.get(path):
            continue
        rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
        restamped.extend(_restamp_mirrors_of(repo_root, mirrors, rel, new_hash[:12]))
    return restamped


def settle_version(
    repo_root: Path,
    version: str,
    *,
    regenerate: Callable[[Path], object] = sync_banner,
) -> SettleResult:
    """Rewrites every `*(since <version>, unreleased)*` marker in scope to `*(since <version>)*`,
    then — only when at least one marker actually settled — runs `regenerate` (the real
    banner/snippet-sync refresh in production, `llms_banner.sync_banner`; injectable the same way
    `refusal_reason` takes `fetch`, so a test can stand in a fake without a real network call) and
    restamps the hash portion of every translated mirror whose named English source's bytes ended
    up different from how they started, regardless of *which* step changed them.

    That "regardless of which step" is deliberate, not incidental: `regenerate` runs over the same
    scope this function already rewrote, and a real release's banner/snippet regeneration can
    change an English page that carried no marker of its own at all — a page a marker-only restamp
    would silently skip, leaving its mirror pointing at a stale pre-regeneration hash. Snapshotting
    every in-scope file's hash before either step and diffing against its hash after both is what
    catches that page too, not just the ones this function's own marker rewrite touched.

    Mechanical and idempotent: a marker for a different (including later) version is left
    untouched, and a second run against the same version rewrites nothing further."""
    pattern = _marker_pattern(version)
    replacement = f"since {version})*"
    mirrors = translated_files(repo_root)
    scope = discover_marker_files(repo_root)
    before_hashes = {path: git_blob_hash(path.read_bytes()) for path in scope}

    rewritten, total_markers = _rewrite_markers(repo_root, scope, pattern, replacement)

    restamped: list[str] = []
    if total_markers > 0:
        regenerate(repo_root)
        restamped = _restamp_changed_sources(repo_root, scope, mirrors, before_hashes)

    return SettleResult(
        marker_count=total_markers, rewritten_files=rewritten, restamped_files=restamped
    )


def refusal_reason(
    repo_root: Path,
    version: str,
    *,
    now: float | None = None,
    fetch: Callable[[str], str | None] = fetch_latest_version,
) -> str | None:
    """`None` when the registry currently reports `version` as published for the bellwether
    package (the identical live lookup `scripts/llms_banner`'s docs-vs-published banner uses) — a
    human-readable refusal message otherwise. Offline (no fresh cache, no network answer) refuses
    too: a settle must never run ahead of the publish it is settling. `now`/`fetch` are the same
    test seams `get_published_version` itself takes, so a test never needs a real clock or a real
    network call."""
    published, _cache_age = get_published_version(
        repo_root, now=now, fetch=fetch, allow_network=True
    )
    if published is None:
        return (
            "could not reach the registry (offline, and no fresh cache on disk) -- a settle "
            "must never run ahead of the publish; retry once the registry is reachable"
        )
    if published != version:
        return (
            f"the registry reports the published version is {published!r}, not {version!r} -- "
            "refusing to settle a version that is not live yet"
        )
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Settle '(since <version>, unreleased)' doc markers in-tree, once, right after a "
            "registry publish tags that exact version live."
        )
    )
    parser.add_argument("version", help="the released version, e.g. 0.1.2")
    args = parser.parse_args(argv)

    reason = refusal_reason(REPO_ROOT, args.version)
    if reason is not None:
        print(f"ERROR: {reason}", file=sys.stderr)
        return 1

    result = settle_version(REPO_ROOT, args.version)
    if result.marker_count == 0:
        print(
            f"ERROR: no '(since {args.version}, unreleased)' markers found in-tree -- nothing to "
            "settle (that is a mistake, not a success).",
            file=sys.stderr,
        )
        return 1

    print(f"settled {result.marker_count} marker(s) across {len(result.rewritten_files)} file(s):")
    for rel in result.rewritten_files:
        print(f"  {rel}")
    if result.restamped_files:
        print(f"restamped {len(result.restamped_files)} translated mirror header(s):")
        for rel in result.restamped_files:
            print(f"  {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
