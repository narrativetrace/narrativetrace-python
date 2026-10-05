# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The version-literal lint: no version talk about NarrativeTrace in a public document.

"No version talk anywhere" is about THIS project's versions (owner ruling 2026-09-24, narrowed by
the same owner 2026-09-25). Repository documentation describes the code it is committed with —
development is trunk-based and `main` IS the published code, since the public snapshot and the
packages are published together — so no README, guide, `llms.txt` or `llms-full.md` says which
version it describes or which one is published. The ONE version literal a
public document may carry for this project is an **install coordinate** (a snippet that cannot be
pasted is not a quickstart), and that one is machine-written: :func:`sync` substitutes the root
`pyproject.toml`'s own `version` into every coordinate form, :func:`check` fails the build on a
coordinate pinned anywhere else. `poe snippet-sync` is the only writer, `poe snippet-check` (inside
`poe check`) the reader — exactly the split `scripts/snippet_check.py` already draws for the
embedded code blocks these rules sit beside.

Two rules, and deliberately no third. :func:`check` reports, each naming file and line:

1. a NarrativeTrace coordinate pinned to a version other than the version source;
2. a `*(since X)*` / `*(since X, unreleased)*` marker, a docs-vs-published banner line, the
   published-version cache comment — the machinery the ruling removed, so a reintroduction fails
   the build rather than rotting back in.

A version literal that is not one of OURS is not this lint's business, and the third rule that
used to make it one — "any other three-part literal", with a reviewed allowlist buying each hit
back — was retired on 2026-09-25 before this port ever built it. The installation guide's
compatibility table, a `structlog==25.1.0` in an example, an advisory note's "1.5.15 → 1.5.38":
every one of those is a fact about somebody else's release rather than version talk about
NarrativeTrace, so every real hit the rule ever produced needed an exemption, and the allowlist
holding them was a second copy of other projects' release notes that went stale on each bump.

A marker-shaped string inside a fenced block is still a marker: fenced blocks are where the install
snippets live, so exempting them would blind this gate on the surface that matters most. A page
that needs to *discuss* the marker syntax writes a placeholder instead.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.translation_check import git_blob_hash, parse_header, translated_files

#: `1.2.3`, `1.2.3rc1`, `1.2.3.dev0` — two or more dotted numbers, an optional PEP 440 suffix.
_VERSION = r"\d+(?:\.\d+)+(?:[-.]?[A-Za-z0-9.+]+)?"
#: Every install-coordinate form this repository's documentation writes: `uv add narrativetrace==X`,
#: `pip install narrativetrace[structlog]==X`, `narrativetrace>=X` inside a `pyproject.toml`
#: snippet, `uv run --with narrativetrace-pytest==X`. The leading guard is what keeps
#: `narrativetracex==9.9.9` — somebody else's distribution — out of the match.
_COORDINATE = re.compile(
    rf"(?<![\w.-])(narrativetrace(?:-[a-z0-9]+)*(?:\[[^\]\s]*\])?\s*(?:==|>=|~=)\s*)({_VERSION})"
)

_SINCE_MARKER = re.compile(r"\*\(since\b")
# The two shapes `scripts/llms_banner.py` wrote under `documentation/llms.txt`'s H1 before the
# ruling removed it, and the cache-age comment it appended to either of them.
_BANNER_MARKER = re.compile(r"\*\((?:Docs and published both at|These docs describe)\b")
_CACHE_COMMENT = re.compile(r"<!--\s*registry checked\b")


_VERSION_SOURCE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def read_version(repo_root: Path) -> str:
    """This repository's one version source, read the way `scripts/publish-public.sh#detect_version`
    reads it: the first `version = "..."` line in the root `pyproject.toml`. A file without one is
    an authoring bug, not a degrade case, so this raises rather than guessing."""
    text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    match = _VERSION_SOURCE.search(text)
    if match is None:
        raise ValueError("pyproject.toml: no top-level 'version = \"...\"' line found")
    return match.group(1)


def _first_line(path: Path) -> str:
    with path.open(encoding="utf-8") as handle:
        return handle.readline().rstrip("\n").rstrip("\r")


def _root_readmes(repo_root: Path) -> list[Path]:
    """The root `README.md` and its language mirrors — found the way every other check here finds a
    mirror (a line-1 header naming `README.md` as its source), never a hardcoded filename list, so
    a fifth language needs no change."""
    readme = repo_root / "README.md"
    pages = [readme] if readme.is_file() else []
    for path in sorted(repo_root.glob("*.md")):
        if path.name == "README.md":
            continue
        header = parse_header(_first_line(path))
        if header is not None and header.source_path == "README.md":
            pages.append(path)
    return pages


def _documentation_pages(repo_root: Path) -> list[Path]:
    """Every `*.md` and `llms.txt` anywhere under `documentation/`, translated mirrors included —
    an install coordinate and a marker are both language-neutral."""
    documentation = repo_root / "documentation"
    if not documentation.is_dir():
        return []
    return sorted(
        path
        for path in documentation.rglob("*")
        if path.is_file() and (path.suffix == ".md" or path.name == "llms.txt")
    )


def _package_readmes(repo_root: Path) -> list[Path]:
    """One `README.md` per distribution under `packages/` — the page PyPI renders."""
    packages = repo_root / "packages"
    if not packages.is_dir():
        return []
    return sorted(
        path / "README.md" for path in packages.iterdir() if (path / "README.md").is_file()
    )


def governed_files(repo_root: Path) -> list[Path]:
    """Every public document this lint governs, in discovery order, each listed once."""
    pages = _root_readmes(repo_root) + _documentation_pages(repo_root) + _package_readmes(repo_root)
    seen: set[Path] = set()
    unique = []
    for path in pages:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def _relative(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _restamp_mirrors_of(repo_root: Path, rewritten_sources: set[str]) -> list[str]:
    """Restamps the line-1 blob hash — the hash only, never the `translated`/`reviewed` dates a
    human set — of every translated mirror whose English source this run rewrote, so a version bump
    leaves `poe translation-check` green in the same pass."""
    if not rewritten_sources:
        return []
    restamped = []
    for mirror in translated_files(repo_root):
        first_line = _first_line(mirror)
        header = parse_header(first_line)
        if header is None or header.source_path not in rewritten_sources:
            continue
        fresh = git_blob_hash((repo_root / header.source_path).read_bytes())[:12]
        if fresh == header.blob_hash_prefix:
            continue
        head = first_line.replace(f"blob {header.blob_hash_prefix}", f"blob {fresh}")
        _, _, rest = mirror.read_text(encoding="utf-8").partition("\n")
        mirror.write_text(f"{head}\n{rest}", encoding="utf-8")
        restamped.append(f"{_relative(repo_root, mirror)}: blob hash restamped")
    return restamped


def sync(repo_root: Path, version: str) -> list[str]:
    """Rewrites every NarrativeTrace install coordinate in every governed document to `version`,
    translated mirrors included (a coordinate is language-neutral), then restamps the mirrors of
    every English page it touched. Returns one line per file changed, sorted; empty when nothing
    needed it. This is the ONLY writer of a coordinate — never hand-type one into a page."""
    changes = []
    rewritten_sources: set[str] = set()
    for path in governed_files(repo_root):
        original = path.read_text(encoding="utf-8")
        rewritten = _COORDINATE.sub(lambda match: match.group(1) + version, original)
        if rewritten == original:
            continue
        path.write_text(rewritten, encoding="utf-8")
        relative = _relative(repo_root, path)
        rewritten_sources.add(relative)
        changes.append(f"{relative}: install coordinate -> {version}")
    changes.extend(_restamp_mirrors_of(repo_root, rewritten_sources))
    return sorted(changes)


def _marker_problems(relative: str, number: int, line: str) -> list[str]:
    """Every retired-machinery marker on one line: a since-marker, a docs-vs-published banner, the
    published-version cache comment. Line-based on purpose — a marker survives a Markdown hard wrap
    only right after `since` or right after the version's comma, and `*(since` is intact either
    way, so no shape a wrap can produce hides from this."""
    problems = []
    if _SINCE_MARKER.search(line):
        problems.append(
            f"{relative}:{number}: a *(since …)* marker is version talk — state the behaviour in "
            f"the present tense instead"
        )
    if _BANNER_MARKER.search(line):
        problems.append(
            f"{relative}:{number}: the docs-vs-published banner was removed — documentation "
            f"describes the code it ships with"
        )
    if _CACHE_COMMENT.search(line):
        problems.append(
            f"{relative}:{number}: the published-version cache was removed — delete the comment"
        )
    return problems


def _coordinate_problems(relative: str, number: int, line: str, version: str) -> list[str]:
    """Every NarrativeTrace install coordinate on one line pinned to something other than the
    version source. A coordinate belonging to anyone else is not this lint's business."""
    return [
        f"{relative}:{number}: NarrativeTrace coordinate pinned to {pinned} but this "
        f"repository is at {version} — run 'poe snippet-sync', never hand-type a coordinate"
        for _, pinned in _COORDINATE.findall(line)
        if pinned != version
    ]


def check(repo_root: Path, version: str) -> list[str]:
    """Every version-talk problem across every governed document, in file/line order."""
    problems: list[str] = []
    for path in governed_files(repo_root):
        relative = _relative(repo_root, path)
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), start=1):
            problems.extend(_marker_problems(relative, number, line))
            problems.extend(_coordinate_problems(relative, number, line, version))
    return problems
