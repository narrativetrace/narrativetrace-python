# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The Context7 gate (`poe context7-check`, wired into `poe check`).

Context7 indexes a public repository's Markdown and serves its code blocks to coding agents. Three
things must stay true for that to work, and each is checked here, offline, from files and git only:

1. `context7.json` validates against the committed copy of Context7's schema
   (`config/context7/context7.schema.json`, fetch date in `SCHEMA-FETCHED.txt`);
2. its `previousVersions` equal this repository's `v*` tags, newest first -- derived, never typed,
   so a release that forgets to update the file fails the build;
3. every opening code fence in a file Context7 will index carries a language tag -- an untagged
   block indexes as prose.

The indexed set follows Context7's own rules (https://context7.com/docs/library-owners): root-level
Markdown is always included, `folders` narrows the rest, `excludeFolders` wins over `folders`,
`excludeFiles` are bare file names. Paths the public snapshot strips (`.publishignore`) are never
indexed, so they are skipped here too.
"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess  # nosec B404 - one fixed read-only `git tag` argv below
import sys
from pathlib import Path
from typing import Any

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.translation_check import REPO_ROOT

CONFIG_NAME = "context7.json"
SCHEMA_PATH = "config/context7/context7.schema.json"
#: File types Context7 parses (https://context7.com/docs/adding-libraries, "What Gets Indexed").
INDEXED_SUFFIXES = frozenset({".md", ".mdx", ".markdown", ".rst", ".txt", ".ipynb"})

_FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")


def load_config(repo_root: Path) -> dict[str, Any]:
    """Parses `context7.json` at the repository root."""
    config = json.loads((repo_root / CONFIG_NAME).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"{CONFIG_NAME}: the top level must be an object")
    return config


def _strings(config: dict[str, Any], key: str) -> list[str]:
    value = config.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{CONFIG_NAME}: {key} must be a list of strings")
    return value


def _under(relative: str, folder: str) -> bool:
    """True when `relative` is `folder` or inside it -- a delimiter-bounded prefix, so `docs` never
    matches `docs-extra/x.md`."""
    folder = folder.strip("/").removeprefix("./")
    return relative == folder or relative.startswith(folder + "/")


def _stripped_patterns(repo_root: Path) -> list[str]:
    ignore = repo_root / ".publishignore"
    if not ignore.is_file():
        return []
    lines = (line.strip() for line in ignore.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def _is_stripped(relative: str, patterns: list[str]) -> bool:
    name = relative.rsplit("/", 1)[-1]
    return any(
        fnmatch.fnmatch(name, pattern)
        or fnmatch.fnmatch(relative, pattern)
        or _under(relative, pattern)
        for pattern in patterns
    )


def _is_selected(relative: str, config: dict[str, Any]) -> bool:
    if any(_under(relative, folder) for folder in _strings(config, "excludeFolders")):
        return False
    if relative.rsplit("/", 1)[-1] in _strings(config, "excludeFiles"):
        return False
    folders = _strings(config, "folders")
    return "/" not in relative or not folders or any(_under(relative, f) for f in folders)


def indexed_files(repo_root: Path, config: dict[str, Any]) -> list[Path]:
    """Every file Context7 will parse for this configuration, sorted, relative to nothing -- real
    paths under `repo_root`. Only tracked-style trees are walked: `.git`, virtualenvs and build
    output are never documentation."""
    stripped = _stripped_patterns(repo_root)
    found = []
    for path in sorted(repo_root.rglob("*")):
        relative = path.relative_to(repo_root).as_posix()
        if not path.is_file() or path.suffix not in INDEXED_SUFFIXES:
            continue
        if relative.startswith((".git/", ".venv")) or "/." in relative:
            continue
        if _is_selected(relative, config) and not _is_stripped(relative, stripped):
            found.append(path)
    return found


def untagged_fences(text: str) -> list[int]:
    """1-based line numbers of every opening code fence with no language tag. Follows CommonMark:
    a closing fence uses the same character, is at least as long as the opener and carries no info
    string, so a fence-looking line inside a block is content, not an opener."""
    problems: list[int] = []
    opener: tuple[str, int] | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        match = _FENCE.match(line)
        if match is None:
            continue
        marker, info = match.group(1), match.group(2).strip()
        if opener is None:
            opener = (marker[0], len(marker))
            if not info:
                problems.append(number)
        elif marker[0] == opener[0] and len(marker) >= opener[1] and not info:
            opener = None
    return problems


def check_fences(repo_root: Path, config: dict[str, Any]) -> list[str]:
    """One problem per untagged opening fence in an indexed file."""
    problems: list[str] = []
    for path in indexed_files(repo_root, config):
        relative = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8")
        problems.extend(
            f"{relative}:{number}: code fence has no language tag (Context7 indexes it as prose)"
            for number in untagged_fences(text)
        )
    return problems


def is_git_checkout(repo_root: Path) -> bool:
    """Whether `repo_root` sits inside a git work tree -- the public snapshot is verified as a
    plain tree staged without one, so a rule derived from the tags has nothing to read there."""
    done = subprocess.run(  # nosec B603, B607 - fixed argv, no shell, read-only git query
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    return done.returncode == 0


def release_tags(repo_root: Path) -> list[str]:
    """The repository's `v*` tags, newest first -- what `previousVersions` derives from."""
    done = subprocess.run(  # nosec B603, B607 - fixed argv, no shell, read-only git query
        ["git", "tag", "--list", "v*", "--sort=-v:refname"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.split()


def check_previous_versions(repo_root: Path, config: dict[str, Any]) -> list[str]:
    """`previousVersions` must be exactly the `v*` tags, newest first, as `{"tag": ...}` objects.

    Outside a git checkout (the staged public snapshot) there are no tags to derive from, so the
    rule passes: the checkout the snapshot was staged from has already run it.
    """
    if not is_git_checkout(repo_root):
        return []
    expected = [{"tag": tag} for tag in release_tags(repo_root)]
    if config.get("previousVersions", []) == expected:
        return []
    return [
        f"{CONFIG_NAME}: previousVersions must equal the v* tags newest first "
        f"({[entry['tag'] for entry in expected]}) -- regenerate it from `git tag --list 'v*' "
        f"--sort=-v:refname`"
    ]


def check_schema(repo_root: Path, config: dict[str, Any]) -> list[str]:
    """Validates the config against the committed Context7 schema; one problem per violation."""
    schema = json.loads((repo_root / SCHEMA_PATH).read_text(encoding="utf-8"))
    validator = jsonschema.Draft7Validator(schema, format_checker=jsonschema.FormatChecker())
    return [
        f"{CONFIG_NAME}: {'/'.join(str(part) for part in error.absolute_path) or '<root>'}: "
        f"{error.message}"
        for error in sorted(validator.iter_errors(config), key=lambda e: list(map(str, e.path)))
    ]


def check(repo_root: Path) -> list[str]:
    """Every problem the three Context7 rules find; empty when the tree is index-ready."""
    if not (repo_root / CONFIG_NAME).is_file():
        return [f"{CONFIG_NAME}: missing at the repository root"]
    config = load_config(repo_root)
    return (
        check_schema(repo_root, config)
        + check_previous_versions(repo_root, config)
        + check_fences(repo_root, config)
    )


def main() -> int:
    problems = check(REPO_ROOT)
    if problems:
        print("ERROR: context7-check found a tree Context7 would mis-index:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(
        "context7-check: context7.json is valid, previousVersions match the tags, "
        "every indexed fence is tagged"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
