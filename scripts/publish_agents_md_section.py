# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Publish-pipeline step (``scripts/publish-public.sh``): composes the public snapshot's
``AGENTS.md`` from just its ``<!-- narrativetrace:skills:start/end -->`` managed section.

``AGENTS.md`` itself is a private agent-orientation file — ``.publishignore`` strips it whole, the
same line as ``CLAUDE.md`` — but its managed skills section is committed BUILD OUTPUT from the
typed ``narrativetrace_skills`` catalogue, the same class as ``.claude/skills/*/SKILL.md``
(``documentation/what-to-commit.md``'s build-output-commit table names both), and ships the same
way. Reads the section from the PRIVATE tree's own (never-stripped) ``AGENTS.md`` — by the time
this runs in the real pipeline the staged copy has already lost the file to ``.publishignore`` —
and writes a fresh, section-only ``AGENTS.md`` into the stage.

Mirrors the TypeScript port's ``tools/publish-agents-md-section-cli.ts`` fix for the identical
what-to-commit.md gap (2026-09-13): the same class of artifact
(``.claude/skills/**/SKILL.md``) has always shipped correctly here because Python's own
``.publishignore`` never stripped ``.claude/`` wholesale in the first place; only the other half of
that row — ``AGENTS.md``'s managed section — had never actually reached a published snapshot,
because nothing composed a stand-in file once the private one was gone. Caught by running
``packages/narrativetrace/tests/test_skills_render.py`` against a fully staged tree, not just a
partial (header-stamp-only) reproduction, where it drifted against ``_check_all()`` because the
committed drift check found no ``AGENTS.md`` at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from narrativetrace_skills import extract_agents_md_section
from scripts.translation_check import REPO_ROOT


def compose_public_agents_md(source_agents_md: Path, stage_root: Path) -> str:
    """Writes ``stage_root/AGENTS.md`` from ``source_agents_md``'s managed section alone. Returns
    the section text written (without the trailing newline the file itself carries)."""
    section = extract_agents_md_section(source_agents_md.read_text(encoding="utf-8"))
    if section is None:
        raise ValueError(
            f"{source_agents_md} has no narrativetrace:skills section to extract "
            f"(markers {source_agents_md.name!r} should carry are missing)"
        )
    (stage_root / "AGENTS.md").write_text(f"{section}\n", encoding="utf-8")
    return section


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Usage: python scripts/publish_agents_md_section.py <stage_root>", file=sys.stderr)
        return 1
    stage_root = Path(args[0])
    try:
        compose_public_agents_md(REPO_ROOT / "AGENTS.md", stage_root)
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("wrote AGENTS.md (managed section only)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
