# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Per-commit gate (wired into ``poe check``): ``.claude/skills/**/SKILL.md``,
``.agents/skills/**/SKILL.md`` and this repository's own ``AGENTS.md`` managed section are BUILD
OUTPUT of the typed catalogue (``narrativetrace_skills``) — never hand-edited. Mirrors
``scripts/check_no_license_headers.py``'s --check/--fix pair: --check fails naming what drifted
(run ``python scripts/skills_render.py --fix`` to fix it); --fix writes it.

``_strip_license_header`` is ``scripts/snippet_check.py``'s own fix for the same gap this had
until this module existed: ``add-narrative-tracing``'s steps embed real source
(``examples/sixty_seconds/*.py``) verbatim, and the publish pipeline's header stamp adds a BSL
preface to every staged source file — in-tree sources never carry it, so a published snapshot's
stamped example would no longer match this repo's own committed ``SKILL.md`` without this strip.
"""

from __future__ import annotations

import sys
from pathlib import Path

from narrativetrace_skills import (
    PRO_LISTINGS,
    SKILLS,
    render_agents_md_snippet,
    render_claude_skill,
    render_codex_skill,
    splice_agents_md_section,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.snippet_check import _strip_license_header
from scripts.translation_check import REPO_ROOT


# Every OUTPUT path is derived from a `root` the caller names (defaulting to this repository), so
# a test can exercise `_fix_all` in a `tmp_path` tree instead of writing tracked files -- these
# tests also run inside the mutmut sandbox, where the mutated catalogue renderer would otherwise
# write a mutant's SKILL.md/AGENTS.md into the real tree (2026-09-17 nightly finding F2's second
# writer). Snippet SOURCES stay rooted at REPO_ROOT: `_resolve_snippet` only ever reads.
def _agents_md_path(root: Path = REPO_ROOT) -> Path:
    return root / "AGENTS.md"


def _resolve_snippet(path: str) -> str:
    content = _strip_license_header((REPO_ROOT / path).read_text(encoding="utf-8"))
    return content.rstrip("\n")


def _claude_skill_md_path(canonical_name: str, root: Path = REPO_ROOT) -> Path:
    return root / ".claude" / "skills" / canonical_name / "SKILL.md"


def _codex_skill_md_path(canonical_name: str, root: Path = REPO_ROOT) -> Path:
    return root / ".agents" / "skills" / canonical_name / "SKILL.md"


def _rendered_skill_files(root: Path = REPO_ROOT) -> dict[Path, str]:
    rendered: dict[Path, str] = {}
    for skill in SKILLS:
        rendered[_claude_skill_md_path(skill.canonical_name, root)] = (
            f"{render_claude_skill(skill, _resolve_snippet)}\n"
        )
        rendered[_codex_skill_md_path(skill.canonical_name, root)] = (
            f"{render_codex_skill(skill, _resolve_snippet)}\n"
        )
    return rendered


def _rendered_agents_md(root: Path = REPO_ROOT) -> str:
    path = _agents_md_path(root)
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    return splice_agents_md_section(current, render_agents_md_snippet(SKILLS, PRO_LISTINGS))


def _check_all(root: Path = REPO_ROOT) -> list[Path]:
    drifted = [
        path
        for path, expected in _rendered_skill_files(root).items()
        if not path.is_file() or path.read_text(encoding="utf-8") != expected
    ]
    agents_md = _agents_md_path(root)
    expected_agents_md = _rendered_agents_md(root)
    if not agents_md.is_file() or agents_md.read_text(encoding="utf-8") != expected_agents_md:
        drifted.append(agents_md)
    return drifted


def _fix_all(root: Path = REPO_ROOT) -> list[Path]:
    written: list[Path] = []
    for path, content in _rendered_skill_files(root).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    agents_md = _agents_md_path(root)
    agents_md.write_text(_rendered_agents_md(root), encoding="utf-8")
    written.append(agents_md)
    return written


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    mode = args[0] if args else None
    if mode not in ("--check", "--fix"):
        print("Usage: python scripts/skills_render.py --check|--fix", file=sys.stderr)
        return 1
    if mode == "--check":
        drifted = _check_all()
        if drifted:
            names = ", ".join(str(path.relative_to(REPO_ROOT)) for path in drifted)
            print(
                f"{len(drifted)} skill artifact(s) do not match the typed catalogue: {names}\n"
                "Run `python scripts/skills_render.py --fix` to regenerate them.",
                file=sys.stderr,
            )
            return 1
        print("skills_render: SKILL.md and AGENTS.md match the typed catalogue")
        return 0
    for path in _fix_all():
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
