# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Per-commit lint against audit-ledger history and port-framing left behind in code comments
(`poe comment-hygiene`, wired into `poe check` next to `contract-lint`).

A code comment carries the constraint a reader of this runtime alone must respect, not the ledger
entry that produced it, and not this runtime's place in a multi-language family -- both belong in
the commit that made the change (or in `documentation/`), never in a comment that survives it and
reads as though it is addressed to a maintainer of every port at once. Two independently-triggering
patterns, both scoped to `packages/*/src/**/*.py` -- never `tests/`, `scripts/`, or
`documentation/`:

- `HISTORY_PATTERN`: an audit-ledger citation surviving in a comment or docstring -- an
  owner-ruling reference, a `ruled 20YY-...` phrase, a bare `(20YY-MM-DD)` audit date, or
  shipped-release wording (`, unreleased)`).
- `PORT_FRAMING_PATTERN`: language that frames this runtime as secondary to another one, inside a
  comment a reader of this runtime alone would see -- "golden source", "the Java
  repo/runtime/implementation", a framing verb before Java ("mirrors", "matches", "ported from",
  "like", "follows", ...), "Java's", or a Java class or ledger citation used as the reference
  (``Java `X` ``, "(Java X", "Java B-123"). Case-insensitive for the phrases, case-sensitive for the
  cross-references. A genuine cross-runtime contract is stated as a family contract ("the same in
  every NarrativeTrace runtime"); `Java` alone (a JVM-interop fact, `JavaScript`) is not flagged.

The walk is plain: visit each package's own `src`, collect hits, excuse exactly the files a JSON
allowlist (file -> reason) names, and flag an allowlist entry whose file no longer has any hit as
stale -- the allowlist is meant to shrink, one package's wave at a time, never to accumulate
entries nobody has to remove.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
ALLOWLIST_PATH: Final = REPO_ROOT / "scripts" / "comment-hygiene-allowlist.json"

HISTORY_PATTERN: Final = re.compile(
    r"owner ruling|ruled 20\d\d|\(20\d\d-\d\d-\d\d\)|, unreleased\)"
)
_PORT_FRAMING_PHRASES: Final = re.compile(
    r"golden (source|copy)|reference implementation|"
    r"the Java (repo|runtime|implementation|reference|version|port|edition)|"
    r"the JVM edition|matching the JVM|Java builder|"
    r"(mirrors?|mirroring|matches|matching|ported from|port of|same as|like|as in|replaced by|"
    r"follows?|following|tracks?|tracking|copied from) (the )?Java\b(?!Script)|"
    r"\bJava's\b",
    re.IGNORECASE,
)
# Case-sensitive on purpose: under IGNORECASE `[A-Z]` matches lowercase and "Java virtual machine"
# would become a hit.
_PORT_FRAMING_CROSS_REFERENCES: Final = re.compile(
    r"Java `|\(Java [A-Z]|Java B-\d+|Java [A-Z][a-z]+[A-Z]"
)


class _PortFramingPattern:
    """The port-framing check as one `search`-able object: a case-insensitive phrase/verb regex
    plus a case-sensitive cross-reference regex (a Java class or ledger citation used as the
    reference). `search` returns the first match of either, or `None`."""

    def search(self, text: str) -> re.Match[str] | None:
        return _PORT_FRAMING_PHRASES.search(text) or _PORT_FRAMING_CROSS_REFERENCES.search(text)


PORT_FRAMING_PATTERN: Final = _PortFramingPattern()


@dataclass(frozen=True)
class CommentHygieneHit:
    """One line matching `HISTORY_PATTERN` or `PORT_FRAMING_PATTERN`. `file` is repo-relative,
    POSIX-separated; `line` is 1-indexed; `text` is the matched line, stripped."""

    file: str
    line: int
    text: str
    reason: str  # "history" | "port-framing"


@dataclass(frozen=True)
class LintResult:
    """`violations`: hits outside the allowlist -- a red gate; `poe check` must fail on these.
    `stale_allowlist_entries`: allowlist entries naming a file with zero current hits, sorted."""

    violations: tuple[CommentHygieneHit, ...]
    stale_allowlist_entries: tuple[str, ...]


def packages_source_files(repo_root: Path) -> list[Path]:
    """Every `.py` file under `<repo_root>/packages/<name>/src/**` (any package with a `src`
    directory), sorted. Never `tests/` -- a sibling of `src` in every package, never nested inside
    it -- so this never has to filter test files out by name."""
    packages_root = repo_root / "packages"
    if not packages_root.is_dir():
        return []
    files: list[Path] = []
    for package_dir in sorted(packages_root.iterdir()):
        src = package_dir / "src"
        if src.is_dir():
            files.extend(src.rglob("*.py"))
    return sorted(files)


def _reason_for(text: str) -> str | None:
    if HISTORY_PATTERN.search(text) is not None:
        return "history"
    if PORT_FRAMING_PATTERN.search(text) is not None:
        return "port-framing"
    return None


def find_history_comments(repo_root: Path) -> list[CommentHygieneHit]:
    """Every `HISTORY_PATTERN`/`PORT_FRAMING_PATTERN` hit across `packages_source_files`,
    repo-relative and sorted by file then line -- allowlist filtering is the caller's job (see
    `lint`)."""
    hits: list[CommentHygieneHit] = []
    for path in packages_source_files(repo_root):
        relative = path.relative_to(repo_root).as_posix()
        content = path.read_text(encoding="utf-8")
        for index, line in enumerate(content.splitlines(), start=1):
            reason = _reason_for(line)
            if reason is not None:
                hits.append(
                    CommentHygieneHit(file=relative, line=index, text=line.strip(), reason=reason)
                )
    return hits


def lint(repo_root: Path, allowlist: Mapping[str, str]) -> LintResult:
    """Lints `packages/*/src` for `HISTORY_PATTERN`/`PORT_FRAMING_PATTERN`, excusing exactly the
    files named in `allowlist` (repo-relative, POSIX-separated paths, each mapped to a human
    reason -- enforced by the caller, never read here)."""
    hits = find_history_comments(repo_root)
    hit_files = {hit.file for hit in hits}
    violations = tuple(hit for hit in hits if hit.file not in allowlist)
    stale = tuple(sorted(file for file in allowlist if file not in hit_files))
    return LintResult(violations=violations, stale_allowlist_entries=stale)


def _load_allowlist(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a JSON object mapping file -> reason")
    return {str(key): str(value) for key, value in raw.items()}


def main() -> int:
    allowlist = _load_allowlist(ALLOWLIST_PATH)
    result = lint(REPO_ROOT, allowlist)
    allowlist_rel = ALLOWLIST_PATH.relative_to(REPO_ROOT).as_posix()

    if result.violations:
        print(
            f"comment-hygiene: {len(result.violations)} history/port-framing reference(s) "
            "left in code comments:"
        )
        for hit in result.violations:
            print(f"  {hit.file}:{hit.line}: [{hit.reason}] {hit.text}")
        print(f"  (add a reason to {allowlist_rel} only for a package not yet swept)")
        return 1

    if result.stale_allowlist_entries:
        print(
            f"comment-hygiene: {len(result.stale_allowlist_entries)} stale allowlist entry(ies) "
            f"-- no hit left, remove from {allowlist_rel}:"
        )
        for file in result.stale_allowlist_entries:
            print(f"  {file}")
        return 1

    print(
        f"comment-hygiene: packages/*/src is clean ({len(allowlist)} package(s) still "
        "allowlisted, pending their own wave)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
