# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`documentation/contract.yaml` schema + linkage gate (`poe contract-lint`, wired into `poe
check`; docs-vs-published-gate-2026-09-12.md §2/§5.1), mirroring Java's `buildSrc`
`ContractLintSupport.kt` / `ContractDecisionSupport` -- python has no buildSrc-equivalent split
build module, so both live here, side by side, the same way the Kotlin twin does.

Validates `documentation/contract.yaml` itself: the schema parses, every `since` is a real version
string, no two entries make the same claim, every entry's `probe` file exists, every `page#anchor`
pointer resolves to a heading that actually exists (a hand-rolled GitHub-flavoured-Markdown
slugifier, tested against real anchors this repository already links to), and every
`*(since X.Y.Z, unreleased)*` marker anywhere in the English docs has at least one contract.yaml
entry recording that version -- the mechanical link between the inline since-markers (part (a) of
the docs-vs-published-gate family) and this file (part (c)). No network; runs every commit.

`is_applicable`/`decide` carry the holds/fails/not-applicable-before-since decision (ruling 1:
exempt only while `since` is strictly later than the version actually installed) -- exercised both
by `contract-probe/` against a real registry (`scripts/contract_check.py`, nightly) and, offline,
by this module's own fixture tests pinning the class of each historical instance the
docs-vs-published-gate design note names: a doc-cited coordinate that does not resolve, a
documented default the published artifact does not honour (twice, one per language's actual
defect), and a documented config shape with no observable effect.

What this module deliberately does NOT do: run a probe, touch the registry, or install anything --
that is `contract-probe/`'s job (a standalone `uv` project, consuming only PyPI) and
`scripts/contract_check.py`'s (the nightly wrapper around it).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.llms_banner import _unreleased_marker_files
from scripts.translation_check import REPO_ROOT

_SINCE_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

# Reuses the exact marker shape `llms_banner._UNRELEASED_MARKER_RE` already scans for (part (a) of
# the same design note) with a capture group added, so the version cited by a marker -- not just
# its presence -- is available for the since-coverage check below.
_UNRELEASED_MARKER_WITH_VERSION_RE = re.compile(
    r"\*\(since\s+([0-9]+(?:\.[0-9]+)*),\s*unreleased\)\*"
)

_VALID_KINDS = frozenset({"entry-point", "reflectable-default", "probed-default", "config-shape"})

CONTRACT_PATH = REPO_ROOT / "documentation" / "contract.yaml"


@dataclass(frozen=True)
class ContractEntry:
    """One `documentation/contract.yaml` entry. `expect` is the single observed string a probe
    must produce for the claim to hold -- the YAML spells it `documented_default`
    (reflectable-default, probed-default) or `expected_effect` (config-shape); both land here as
    one field, since every probe this repo runs already reduces to "one string, compared for
    equality" regardless of which document field named it. `coordinate`/`registry` apply to
    entry-point only; `probe` names the source file (relative to the repo root) implementing the
    check -- required for every kind so a reader always finds the code proving the claim next to
    the claim itself."""

    id: str
    kind: str
    page: str
    claim: str
    since: str
    expect: str
    probe: str
    coordinate: str | None = None
    registry: str | None = None


@dataclass(frozen=True)
class ContractDocument:
    version_source: str
    entries: list[ContractEntry]


@dataclass(frozen=True)
class ContractPageRef:
    """One page-anchor pointer, split for validation (`heading_anchors` builds the target's real
    anchor set)."""

    relative_path: str
    anchor: str


def slugify(heading: str) -> str:
    """The GitHub-flavoured-Markdown heading slug: lowercase, strip anything but
    `[a-z0-9 _-]`, then turn spaces into hyphens. Deliberately does not collapse repeated
    hyphens/spaces (a heading with an em dash or a slash between two words legitimately slugs to
    a double hyphen) -- matching the algorithm GitHub's own renderer uses, so an anchor validated
    here is also the one a reader's click actually lands on."""
    lowered = heading.lower()
    kept = "".join(ch for ch in lowered if ch.isalnum() or ch in " -_")
    return kept.replace(" ", "-")


def heading_anchors(markdown_path: Path) -> set[str]:
    """Every anchor slug the given Markdown file's headings produce, in document order, with
    GitHub's own disambiguation for a repeated slug (`foo`, `foo-1`, `foo-2`, ...)."""
    seen: dict[str, int] = {}
    anchors: set[str] = set()
    for line in markdown_path.read_text(encoding="utf-8").splitlines():
        match = _HEADING_RE.match(line)
        if match is None:
            continue
        base = slugify(match.group(2))
        count = seen.get(base, 0)
        seen[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def parse_page_ref(page: str) -> ContractPageRef:
    """Splits `"documentation/foo.md#some-anchor"` into path and anchor; raises on a pointer with
    no `#anchor` half -- a contract entry is always about one specific claim, never a whole page."""
    hash_index = page.find("#")
    if hash_index <= 0 or hash_index == len(page) - 1:
        raise ValueError(f'"{page}" -- a contract entry\'s page must be "<path>#<anchor>"')
    return ContractPageRef(page[:hash_index], page[hash_index + 1 :])


def _required_str(path: Path, raw: dict[str, Any], name: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{path}: entry missing "{name}": {raw}')
    return value


def _parse_entry(path: Path, raw: dict[str, Any]) -> ContractEntry:
    entry_id = _required_str(path, raw, "id")
    kind = _required_str(path, raw, "kind")
    if kind not in _VALID_KINDS:
        raise ValueError(f'{path}: unknown kind "{kind}" -- must be one of {sorted(_VALID_KINDS)}')
    expect = raw.get("documented_default")
    if not isinstance(expect, str) or not expect:
        expect = raw.get("expected_effect")
    if not isinstance(expect, str) or not expect:
        raise ValueError(
            f'{path}: entry "{entry_id}" needs "documented_default" or "expected_effect"'
        )
    if kind == "entry-point":
        _required_str(path, raw, "coordinate")
    return ContractEntry(
        id=entry_id,
        kind=kind,
        page=_required_str(path, raw, "page"),
        claim=_required_str(path, raw, "claim"),
        since=_required_str(path, raw, "since"),
        expect=expect,
        probe=_required_str(path, raw, "probe"),
        coordinate=raw.get("coordinate"),
        registry=raw.get("registry"),
    )


def parse(path: Path) -> ContractDocument:
    """Parses `documentation/contract.yaml`. Raises (never returns a partial document) on anything
    the schema does not allow -- a malformed contract must fail loud."""
    root = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not root:
        raise ValueError(f"{path}: empty document")
    version_source = root.get("version_source")
    if not isinstance(version_source, str) or not version_source:
        raise ValueError(f'{path}: missing "version_source"')
    raw_entries = root.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError(f'{path}: missing "entries" list')
    return ContractDocument(version_source, [_parse_entry(path, raw) for raw in raw_entries])


def unreleased_marker_versions(repo_root: Path) -> set[str]:
    """Every version cited by a `*(since X.Y.Z, unreleased)*` marker across the English docs --
    reuses `llms_banner`'s own file-discovery scan (`_unreleased_marker_files`, already shared with
    `snippet_check`'s per-commit gate via `llms_banner.check_banner`) so this and the
    docs-vs-published banner can never quietly disagree about which files count as "the English
    docs"."""
    versions: set[str] = set()
    for path in _unreleased_marker_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        versions.update(_UNRELEASED_MARKER_WITH_VERSION_RE.findall(text))
    return versions


def _lint_duplicates(
    entry: ContractEntry, seen_ids: set[str], seen_claims: dict[str, str]
) -> list[str]:
    problems: list[str] = []
    if entry.id in seen_ids:
        problems.append(f'duplicate entry id "{entry.id}"')
    seen_ids.add(entry.id)

    first_id = seen_claims.get(entry.claim)
    if first_id is not None:
        problems.append(f'"{entry.id}" and "{first_id}" make the same claim: "{entry.claim}"')
    seen_claims[entry.claim] = entry.id
    return problems


def _lint_shape(entry: ContractEntry, repo_root: Path) -> list[str]:
    problems: list[str] = []
    if not _SINCE_PATTERN.match(entry.since):
        problems.append(f'"{entry.id}": since "{entry.since}" is not a real version string (x.y.z)')
    if entry.kind == "entry-point" and not entry.coordinate:
        problems.append(f'"{entry.id}": entry-point requires "coordinate"')
    if not (repo_root / entry.probe).is_file():
        problems.append(f'"{entry.id}": probe "{entry.probe}" does not exist')
    return problems


def _lint_page_ref(entry: ContractEntry, repo_root: Path) -> list[str]:
    try:
        ref = parse_page_ref(entry.page)
    except ValueError as exc:
        return [f'"{entry.id}": {exc}']
    page_file = repo_root / ref.relative_path
    if not page_file.is_file():
        return [f'"{entry.id}": page "{ref.relative_path}" does not exist']
    if ref.anchor not in heading_anchors(page_file):
        return [f'"{entry.id}": anchor "#{ref.anchor}" not found in {ref.relative_path}']
    return []


def _lint_unreleased_coverage(
    covered_versions: set[str], unreleased_versions: set[str]
) -> list[str]:
    problems: list[str] = []
    for version in sorted(unreleased_versions):
        if version not in covered_versions:
            problems.append(
                f'documentation carries "*(since {version}, unreleased)*" but no contract.yaml '
                f'entry has since: "{version}" -- add one in the same commit as the feature '
                f"(docs-vs-published-gate §5.1 ruling 3)"
            )
    return problems


def lint(repo_root: Path, document: ContractDocument, unreleased_versions: set[str]) -> list[str]:
    """Every problem found, empty when the contract is internally consistent. `repo_root` resolves
    `page` and `probe` pointers; `unreleased_versions` is the distinct set of versions cited by
    `*(since X.Y.Z, unreleased)*` across the English docs, passed in rather than re-walked here so
    the two checks can never quietly disagree on which files count as "the English docs"."""
    problems: list[str] = []
    seen_ids: set[str] = set()
    seen_claims: dict[str, str] = {}

    for entry in document.entries:
        problems += _lint_duplicates(entry, seen_ids, seen_claims)
        problems += _lint_shape(entry, repo_root)
        problems += _lint_page_ref(entry, repo_root)

    covered_versions = {entry.since for entry in document.entries}
    problems += _lint_unreleased_coverage(covered_versions, unreleased_versions)
    return sorted(problems)


class ContractVerdict(StrEnum):
    """holds: the probe observed exactly what the docs claim. fails: it observed something else.
    not-applicable-before-since: the claim's `since` is later than the version actually installed
    -- ruling 1 (docs-vs-published-gate §5.1): exempt only while later than the INSTALLED
    published version, never the repo's own."""

    HOLDS = "holds"
    FAILS = "fails"
    NOT_APPLICABLE_BEFORE_SINCE = "not-applicable-before-since"


@dataclass(frozen=True)
class ContractOutcome:
    entry: ContractEntry
    verdict: ContractVerdict
    message: str


def _version_parts(version: str) -> list[int]:
    return [int(part) for part in version.split(".")]


def is_applicable(since: str, installed_version: str) -> bool:
    """True while `since` is NOT strictly later than `installed_version` -- the only case
    docs-vs-published-gate §5.1 ruling 1 exempts a claim from being checked at all. Every `since`
    string is already validated against `_SINCE_PATTERN` before this is ever called."""
    since_parts = _version_parts(since)
    installed_parts = _version_parts(installed_version)
    for i in range(max(len(since_parts), len(installed_parts))):
        x = since_parts[i] if i < len(since_parts) else 0
        y = installed_parts[i] if i < len(installed_parts) else 0
        if x != y:
            return x < y
    return True  # equal versions: since holds AT the installed version, so it is applicable


def decide(entry: ContractEntry, installed_version: str, observed: str | None) -> ContractOutcome:
    """`observed` is `None` when the probe itself could not even run (registry unreachable,
    artifact missing) -- treated as a failure with its own explaining message, never silently
    skipped; only a `since` later than `installed_version` is ever skipped."""
    if not is_applicable(entry.since, installed_version):
        return ContractOutcome(
            entry,
            ContractVerdict.NOT_APPLICABLE_BEFORE_SINCE,
            f'"{entry.id}": since {entry.since} is later than installed {installed_version} '
            f"-- skipped",
        )
    if observed == entry.expect:
        return ContractOutcome(entry, ContractVerdict.HOLDS, f'"{entry.id}": holds')
    coordinate = entry.coordinate or entry.id
    return ContractOutcome(
        entry,
        ContractVerdict.FAILS,
        f'documentation/contract.yaml: {entry.id} documented default "{entry.expect}" '
        f"(since {entry.since}) but {coordinate} {installed_version} (published) reads "
        f'"{observed if observed is not None else "<no answer>"}"',
    )


def check_contract(repo_root: Path = REPO_ROOT) -> list[str]:
    document = parse(repo_root / "documentation" / "contract.yaml")
    return lint(repo_root, document, unreleased_marker_versions(repo_root))


def main() -> int:
    problems = check_contract()
    if not problems:
        print("contract-lint: documentation/contract.yaml is internally consistent")
        return 0
    print("contract-lint: found problems in documentation/contract.yaml:")
    for problem in problems:
        print(f"  {problem}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
