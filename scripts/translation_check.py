# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Translation platform gate (`poe translation-check`, wired into `poe check`).

The translation platform for this repository follows the same conventions as the Java runtime's
own translation build tooling (`ai.narrativetrace.build.Translation*Support`). The i18n
terminology conventions are canonical (this runtime's own copy; the platform-agnostic
product-term table is sourced from the Java runtime's reference copy — see that file's
provenance note).

Four checks run when `documentation/i18n/manifest.json` is present:

- **Staleness** (always, manifest or not): every translated document's line-1 header records the
  blob hash of its English source at translation time; a source edited since then fails the build.
- **Completeness**: every manifest document must exist for every `complete` language (failure); an
  `in-progress` language's gaps are a warning naming the exact list.
- **Structure parity**: heading tree, code-fence *count*, table shapes, and every relative link
  must match/resolve against the English source (failure). Code-fence *content* drift is a warning
  only — comments, `<placeholder>` labels and per-language example arguments are legitimately
  localized, and no dependency-free parser can tell that apart from a real drift.
- **Index/menu integrity**: the English `documentation/README.md` and each language's sibling index
  carry the exact language menu the manifest prescribes; a sibling index lists exactly its
  language's currently-translated documents.

Absent a manifest, this degrades to the staleness-only check, with one warning saying so — a repo
that has not adopted the manifest is never broken by it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_RELATIVE_PATH = "documentation/i18n/manifest.json"
ENGLISH_INDEX = "documentation/README.md"
ENGLISH_NAME = "README.md"

_VALID_STATUSES = {"complete", "in-progress"}

_HEADER_RE = re.compile(
    r"<!-- source: (\S+) blob ([0-9a-f]{12}) \| translated: \d{4}-\d{2}-\d{2}"
    r"(?: \| reviewed: (\d{4}-\d{2}-\d{2}|-))? -->"
)
_HEADING_RE = re.compile(r"^(#{1,6})\s")
_LINK_TARGET_RE = re.compile(r"\[[^\]]*]\(([^)]+)\)")
_EXTERNAL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class I18nLanguage:
    code: str
    display_name: str
    directory: str
    index: str
    root_readme: str
    status: str


@dataclass(frozen=True)
class I18nDocument:
    source: str
    translations: dict[str, str]


@dataclass(frozen=True)
class I18nManifest:
    source_language: str
    languages: list[I18nLanguage]
    documents: list[I18nDocument]


def load_manifest_or_none(repo_root: Path) -> I18nManifest | None:
    """Parses `documentation/i18n/manifest.json`, or `None` when it does not exist yet.

    A present-but-malformed manifest raises (fail fast) rather than degrading — that is a
    configuration error, not the "not adopted yet" case this function otherwise handles gracefully.
    """
    path = repo_root / MANIFEST_RELATIVE_PATH
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    languages = [_parse_language(entry) for entry in raw["languages"]]
    documents = [_parse_document(entry) for entry in raw["documents"]]
    return I18nManifest(raw.get("sourceLanguage", "en"), languages, documents)


def _parse_language(raw: dict[str, object]) -> I18nLanguage:
    status = raw["status"]
    if status not in _VALID_STATUSES:
        raise ValueError(
            f"{MANIFEST_RELATIVE_PATH}: unknown language status '{status}' "
            "(expected 'complete' or 'in-progress')"
        )
    return I18nLanguage(
        code=str(raw["code"]),
        display_name=str(raw["displayName"]),
        directory=str(raw["directory"]),
        index=str(raw["index"]),
        root_readme=str(raw["rootReadme"]),
        status=str(status),
    )


def _parse_document(raw: dict[str, object]) -> I18nDocument:
    raw_translations = raw.get("translations") or {}
    assert isinstance(raw_translations, dict)
    translations = {str(code): str(filename) for code, filename in raw_translations.items()}
    return I18nDocument(source=str(raw["source"]), translations=translations)


# --------------------------------------------------------------------------- #
# Staleness
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TranslationHeader:
    source_path: str
    blob_hash_prefix: str
    reviewed: str | None = None


def parse_header(first_line: str) -> TranslationHeader | None:
    """Parses a staleness header line; `None` when the line is not a valid header."""
    match = _HEADER_RE.fullmatch(first_line.strip())
    if match is None:
        return None
    reviewed = match.group(3)
    if reviewed == "-":
        reviewed = None
    return TranslationHeader(match.group(1), match.group(2), reviewed)


def git_blob_hash(content: bytes) -> str:
    """The git blob hash of `content`: SHA-1 over `b"blob <size>\\0"` + bytes — no git process."""
    digest = hashlib.sha1(usedforsecurity=False)  # nosec B324 - content-addressing, not security
    digest.update(f"blob {len(content)}".encode())
    digest.update(b"\0")
    digest.update(content)
    return digest.hexdigest()


def _first_line(path: Path) -> str:
    with path.open(encoding="utf-8") as handle:
        return handle.readline().rstrip("\n").rstrip("\r")


def _language_directories(repo_root: Path) -> list[Path]:
    """Directories under `documentation/` that hold translated guides, not English topical ones.

    The Java runtime treats every non-`i18n` child of `documentation/` as a language directory —
    sound there, since its guides sit flat in `documentation/`. This runtime nests English topical
    subdirectories (`documentation/guides/`, `documentation/design-notes/`) alongside where
    translations will land, so "every subdirectory" would misclassify them. The manifest already
    declares the real set (`I18nLanguage.directory`); fall back to the Java heuristic only when no
    manifest exists yet, i.e. before any language directory (by any name) exists at all.
    """
    documentation = repo_root / "documentation"
    if not documentation.is_dir():
        return []
    manifest = load_manifest_or_none(repo_root)
    if manifest is not None:
        return [repo_root / language.directory for language in manifest.languages]
    return [
        entry
        for entry in sorted(documentation.iterdir())
        if entry.is_dir() and entry.name != "i18n"
    ]


def _language_directory_files(repo_root: Path) -> list[Path]:
    files = []
    for directory in _language_directories(repo_root):
        if directory.is_dir():
            files.extend(sorted(child for child in directory.iterdir() if child.suffix == ".md"))
    return files


def _headered_markdown_files(repo_root: Path, already_covered: set[Path]) -> list[Path]:
    found = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        current = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d != "build" and not d.startswith(".")]
        for name in filenames:
            if not name.endswith(".md"):
                continue
            candidate = current / name
            if candidate.resolve() in already_covered:
                continue
            if parse_header(_first_line(candidate)) is not None:
                found.append(candidate)
    return found


def translated_files(repo_root: Path) -> list[Path]:
    """Every file this check discovers as a translation, shared by every other check below."""
    language_files = _language_directory_files(repo_root)
    covered = {f.resolve() for f in language_files}
    headered_files = _headered_markdown_files(repo_root, covered)
    return language_files + headered_files


def _relative(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _check_file(repo_root: Path, file: Path) -> str | None:
    relative = _relative(repo_root, file)
    header = parse_header(_first_line(file))
    if header is None:
        return f"{relative}: missing or malformed staleness header on line 1"
    source = repo_root / header.source_path
    try:
        source.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return f"{relative}: source path '{header.source_path}' escapes the repository root"
    if not source.is_file():
        return f"{relative}: source '{header.source_path}' is missing"
    actual = git_blob_hash(source.read_bytes())[:12]
    if actual != header.blob_hash_prefix:
        return (
            f"{relative}: stale — header records {header.blob_hash_prefix} but "
            f"'{header.source_path}' is now {actual}; re-translate the delta and restamp line 1"
        )
    return None


def check_staleness(repo_root: Path) -> list[str]:
    """Every translated document out of sync with its English source, sorted by path."""
    problems = (_check_file(repo_root, f) for f in translated_files(repo_root))
    return sorted(p for p in problems if p is not None)


# --------------------------------------------------------------------------- #
# Completeness
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CompletenessResult:
    failures: list[str]
    warnings: list[str]


def _exists_under_language_directory(
    repo_root: Path, language: I18nLanguage, filename: str
) -> bool:
    return (repo_root / language.directory / filename).is_file()


def _check_language_completeness(
    repo_root: Path, language: I18nLanguage, documents: list[I18nDocument]
) -> tuple[list[str], list[str]]:
    failures = []
    missing = []
    for document in documents:
        translated = document.translations.get(language.code)
        if translated is None:
            missing.append(document.source)
        elif not _exists_under_language_directory(repo_root, language, translated):
            failures.append(
                f"{language.code}: manifest declares '{language.directory}/{translated}' "
                f"for {document.source} but the file does not exist"
            )
    if not missing:
        return failures, []
    message = f"{language.code} ({language.status}): missing translation of " + ", ".join(missing)
    return ([*failures, message], []) if language.status == "complete" else (failures, [message])


def check_completeness(repo_root: Path, manifest: I18nManifest) -> CompletenessResult:
    """Every manifest document, checked against every declared language."""
    failures: list[str] = []
    warnings: list[str] = []
    for language in manifest.languages:
        language_failures, language_warnings = _check_language_completeness(
            repo_root, language, manifest.documents
        )
        failures.extend(language_failures)
        warnings.extend(language_warnings)
    return CompletenessResult(sorted(failures), sorted(warnings))


# --------------------------------------------------------------------------- #
# Structure parity
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class StructureProfile:
    heading_levels: list[int]
    code_blocks: list[str]
    tables: list[tuple[int, int]]


@dataclass(frozen=True)
class StructureComparison:
    failures: list[str]
    warnings: list[str]


def _is_fence_marker(line: str) -> bool:
    return line.lstrip().startswith("```")


def _is_table_line(line: str) -> bool:
    return line.lstrip().startswith("|")


def _is_separator_line(line: str) -> bool:
    return line.strip() != "" and all(c in "|-: \t" for c in line) and "-" in line


def _column_count(header_line: str) -> int:
    trimmed = header_line.strip()
    trimmed = trimmed.removeprefix("|").removesuffix("|")
    return len(trimmed.split("|"))


def _flush_table(lines: list[str], into: list[tuple[int, int]]) -> None:
    if len(lines) < 2 or not _is_separator_line(lines[1]):
        return
    into.append((len(lines) - 2, _column_count(lines[0])))


def _apply_line(
    line: str,
    fence: list[str] | None,
    table: list[str],
    heading_levels: list[int],
    code_blocks: list[str],
    tables: list[tuple[int, int]],
) -> tuple[list[str] | None, list[str]]:
    """One step of `profile`'s line-by-line state machine; returns the next `(fence, table)`."""
    if fence is not None and _is_fence_marker(line):
        code_blocks.append("\n".join(fence))
        return None, table
    if fence is not None:
        fence.append(line)
        return fence, table
    if _is_fence_marker(line):
        return [line], table
    if _is_table_line(line):
        table.append(line)
        return fence, table
    _flush_table(table, tables)
    match = _HEADING_RE.match(line)
    if match:
        heading_levels.append(len(match.group(1)))
    return fence, []


def profile(text: str) -> StructureProfile:
    """Parses `text` into its structural shape, skipping anything inside a fenced code block."""
    heading_levels: list[int] = []
    code_blocks: list[str] = []
    tables: list[tuple[int, int]] = []
    fence: list[str] | None = None
    table: list[str] = []
    for line in text.splitlines():
        fence, table = _apply_line(line, fence, table, heading_levels, code_blocks, tables)
    _flush_table(table, tables)
    return StructureProfile(heading_levels, code_blocks, tables)


def _compare_headings(
    source: list[int], translation: list[int], source_label: str, translation_label: str
) -> list[str]:
    if len(source) != len(translation):
        return [
            f"{translation_label}: heading count {len(translation)} "
            f"vs {source_label}'s {len(source)}"
        ]
    return [
        f"{translation_label}: heading {i + 1} is level {translation[i]}, "
        f"{source_label}'s heading {i + 1} is level {source[i]}"
        for i in range(len(source))
        if source[i] != translation[i]
    ]


def _compare_code_blocks(
    source: list[str], translation: list[str], source_label: str, translation_label: str
) -> tuple[list[str], list[str]]:
    if len(source) != len(translation):
        return [
            f"{translation_label}: code block count {len(translation)} "
            f"vs {source_label}'s {len(source)}"
        ], []
    warnings = [
        f"{translation_label}: code block {i + 1} differs from {source_label} — verify by hand "
        "(translated comments, localized placeholders and per-language example values are expected)"
        for i in range(len(source))
        if source[i] != translation[i]
    ]
    return [], warnings


def _table_shape_mismatch(
    source: tuple[int, int],
    translation: tuple[int, int],
    index: int,
    source_label: str,
    translation_label: str,
) -> str | None:
    if source == translation:
        return None
    parts = []
    if source[0] != translation[0]:
        parts.append(f"rows {translation[0]} vs {source[0]}")
    if source[1] != translation[1]:
        parts.append(f"columns {translation[1]} vs {source[1]}")
    return (
        f"{translation_label}: table {index + 1} shape mismatches {source_label} "
        f"({', '.join(parts)})"
    )


def _compare_tables(
    source: list[tuple[int, int]],
    translation: list[tuple[int, int]],
    source_label: str,
    translation_label: str,
) -> list[str]:
    if len(source) != len(translation):
        return [
            f"{translation_label}: table count {len(translation)} vs {source_label}'s {len(source)}"
        ]
    mismatches = (
        _table_shape_mismatch(source[i], translation[i], i, source_label, translation_label)
        for i in range(len(source))
    )
    return [m for m in mismatches if m is not None]


def compare(
    source: StructureProfile,
    translation: StructureProfile,
    source_label: str,
    translation_label: str,
) -> StructureComparison:
    """Structural differences between `translation` (labeled `translation_label`) and `source`."""
    failures = _compare_headings(
        source.heading_levels, translation.heading_levels, source_label, translation_label
    )
    failures += _compare_tables(source.tables, translation.tables, source_label, translation_label)
    code_failures, code_warnings = _compare_code_blocks(
        source.code_blocks, translation.code_blocks, source_label, translation_label
    )
    failures += code_failures
    return StructureComparison(failures, code_warnings)


def _without_fenced_lines(text: str) -> str:
    fenced = False
    kept = []
    for line in text.splitlines():
        marker = _is_fence_marker(line)
        if marker:
            fenced = not fenced
        if not fenced and not marker:
            kept.append(line)
    return "\n".join(kept)


def broken_links(file: Path, repo_root: Path) -> list[str]:
    """Relative links in `file` that don't resolve to a file/directory; external/anchors skipped."""
    label = _relative(repo_root, file)
    non_fenced = _without_fenced_lines(file.read_text(encoding="utf-8"))
    targets = []
    seen = set()
    for match in _LINK_TARGET_RE.finditer(non_fenced):
        target = match.group(1).split("#", 1)[0].strip()
        if not target or _EXTERNAL_SCHEME_RE.match(target) or target in seen:
            continue
        seen.add(target)
        resolved = file.parent / target
        if not resolved.is_file() and not resolved.is_dir():
            targets.append(f"{label}: link target '{target}' does not resolve")
    return targets


def _check_one_structure(repo_root: Path, file: Path) -> StructureComparison:
    header = parse_header(_first_line(file))
    if header is None:
        return StructureComparison([], [])
    source = repo_root / header.source_path
    if not source.is_file():
        return StructureComparison([], [])
    label = _relative(repo_root, file)
    structural = compare(
        profile(source.read_text(encoding="utf-8")),
        profile(file.read_text(encoding="utf-8")),
        header.source_path,
        label,
    )
    return StructureComparison(
        structural.failures + broken_links(file, repo_root), structural.warnings
    )


def check_all_structure(repo_root: Path) -> StructureComparison:
    """Structure parity across every discovered translation with a resolvable header and source."""
    failures: list[str] = []
    warnings: list[str] = []
    for file in translated_files(repo_root):
        result = _check_one_structure(repo_root, file)
        failures.extend(result.failures)
        warnings.extend(result.warnings)
    return StructureComparison(sorted(failures), sorted(warnings))


# --------------------------------------------------------------------------- #
# Index / menu integrity
# --------------------------------------------------------------------------- #


def menu_line(text: str) -> str | None:
    """The first non-blank line after the document's H1, or `None` when there is no H1."""
    lines = text.splitlines()
    h1_index = next((i for i, line in enumerate(lines) if line.lstrip().startswith("# ")), None)
    if h1_index is None:
        return None
    for line in lines[h1_index + 1 :]:
        if line.strip():
            return line.strip()
    return None


def _language_segment(repo_root: Path, language: I18nLanguage, current_code: str | None) -> str:
    if language.code == current_code:
        return f"**{language.display_name}**"
    if (repo_root / language.index).is_file():
        return f"[{language.display_name}]({Path(language.index).name})"
    return language.display_name


def expected_menu(manifest: I18nManifest, repo_root: Path, current_code: str | None) -> str:
    """The language-menu line this repository's convention prescribes for `current_code`'s page."""
    segments = [f"[English]({ENGLISH_NAME})"]
    segments += [
        _language_segment(repo_root, language, current_code) for language in manifest.languages
    ]
    return " | ".join(segments)


def document_targets(text: str) -> list[str]:
    """The link targets named in this index's document table rows (menu-line links excluded)."""
    targets: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("|") and not _is_separator_line(line):
            targets.extend(match.group(1) for match in _LINK_TARGET_RE.finditer(line))
    return targets


def _check_menu(label: str, text: str, expected: str) -> str | None:
    actual = menu_line(text)
    if actual == expected:
        return None
    return f"{label}: language menu is '{actual}', expected '{expected}'"


def _check_rows(
    index_file: Path, label: str, text: str, manifest: I18nManifest, language: I18nLanguage
) -> list[str]:
    dir_name = Path(language.directory).name
    expected = {
        f"{dir_name}/{doc.translations[language.code]}"
        for doc in manifest.documents
        if language.code in doc.translations
    }
    actual = set(document_targets(text))
    problems = [
        f"{label}: missing an index row for '{target}'" for target in sorted(expected - actual)
    ]
    problems += [
        f"{label}: index row '{target}' is not a manifest document for '{language.code}'"
        for target in sorted(actual - expected)
    ]
    problems += [
        f"{label}: row target '{target}' does not resolve"
        for target in sorted(actual)
        if not (index_file.parent / target).is_file()
    ]
    return problems


def check_language_index(
    repo_root: Path, manifest: I18nManifest, language: I18nLanguage
) -> list[str]:
    """Problems in `language`'s own sibling index: existence, menu line, row set, row targets."""
    index_file = repo_root / language.index
    if not index_file.is_file():
        if language.status == "complete":
            return [
                f"{language.index}: missing — '{language.code}' is declared complete "
                "but has no sibling index"
            ]
        return []
    text = index_file.read_text(encoding="utf-8")
    problems = []
    menu_problem = _check_menu(
        language.index, text, expected_menu(manifest, repo_root, language.code)
    )
    if menu_problem:
        problems.append(menu_problem)
    problems += _check_rows(index_file, language.index, text, manifest, language)
    return problems


def check_english_index_menu(repo_root: Path, manifest: I18nManifest) -> list[str]:
    """Problems in the English `documentation/README.md` menu."""
    index_file = repo_root / ENGLISH_INDEX
    if not index_file.is_file():
        return [f"{ENGLISH_INDEX}: missing"]
    expected = expected_menu(manifest, repo_root, None)
    actual = menu_line(index_file.read_text(encoding="utf-8"))
    if actual != expected:
        return [f"{ENGLISH_INDEX}: language menu is '{actual}', expected '{expected}'"]
    return []


def check_all_index(repo_root: Path, manifest: I18nManifest) -> list[str]:
    """Every index/menu problem: the English menu plus every declared language's own index."""
    problems = check_english_index_menu(repo_root, manifest)
    for language in manifest.languages:
        problems += check_language_index(repo_root, manifest, language)
    return problems


# --------------------------------------------------------------------------- #
# Review field (warn-only)
# --------------------------------------------------------------------------- #


def _is_unreviewed(file: Path) -> bool:
    header = parse_header(_first_line(file))
    return header is not None and header.reviewed is None


def unreviewed(repo_root: Path) -> list[str]:
    """Every discovered translation with no `| reviewed:` date — absent and `-` both count."""
    return sorted(_relative(repo_root, f) for f in translated_files(repo_root) if _is_unreviewed(f))


def review_summary_line(repo_root: Path) -> str:
    count = len(unreviewed(repo_root))
    return (
        f"translation-check: {count} translated document(s) unreviewed "
        "(run 'poe translation-status' for the full list)"
    )


def _language_status_line(repo_root: Path, manifest: I18nManifest, language: I18nLanguage) -> str:
    total = len(manifest.documents)
    translated = sum(1 for doc in manifest.documents if language.code in doc.translations)
    unreviewed_in_language = sum(1 for f in unreviewed(repo_root) if f"/{language.code}/" in f)
    return (
        f"  {language.code} ({language.status}): {translated}/{total} translated, "
        f"{unreviewed_in_language} unreviewed"
    )


def status_report(repo_root: Path, manifest: I18nManifest | None) -> str:
    """The human dashboard `poe translation-status` prints: coverage/review counts, per language."""
    if manifest is None:
        return f"translation-status: no manifest at {MANIFEST_RELATIVE_PATH}"
    lines = ["translation-status:"]
    lines += [
        _language_status_line(repo_root, manifest, language) for language in manifest.languages
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Orchestrator + CLI
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TranslationPlatformResult:
    failures: list[str]
    warnings: list[str]


def run_all(repo_root: Path) -> TranslationPlatformResult:
    """Runs every check the current tree supports; never raises for a missing manifest."""
    staleness = check_staleness(repo_root)
    manifest = load_manifest_or_none(repo_root)
    if manifest is None:
        return TranslationPlatformResult(
            staleness,
            [
                f"translation-check: no manifest at {MANIFEST_RELATIVE_PATH} — "
                "ran the staleness-only check"
            ],
        )
    completeness = check_completeness(repo_root, manifest)
    structure = check_all_structure(repo_root)
    index = check_all_index(repo_root, manifest)
    failures = staleness + completeness.failures + structure.failures + index
    warnings = completeness.warnings + structure.warnings + [review_summary_line(repo_root)]
    return TranslationPlatformResult(failures, warnings)


def main() -> int:
    result = run_all(REPO_ROOT)
    for warning in result.warnings:
        print(warning)
    if result.failures:
        print("ERROR: translation platform check failed (see the i18n terminology conventions):")
        for failure in result.failures:
            print(f"  {failure}")
        return 1
    print(
        "translation-check: all translated documents are in sync, complete, and correctly indexed"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
