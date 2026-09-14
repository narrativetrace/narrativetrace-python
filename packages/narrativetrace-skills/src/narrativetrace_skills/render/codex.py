# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders a :class:`~narrativetrace_skills.skill.Skill` as a Codex CLI ``SKILL.md``
(frontmatter + body) -- the SAME body :mod:`claude` renders, since Codex's discovery mechanism
does not otherwise differ from what this catalogue already produces.

Codex CLI's skill discovery (verified 2026-09-14 against its own current documentation): a
repository's skills live under ``.agents/skills/<name>/SKILL.md``, scanned from the current
working directory up to the repository root (plus a `$HOME/.agents/skills` user scope and further
admin/system scopes this repository does not populate). Frontmatter needs only two fields --
``name`` and ``description`` -- a strict subset of what :mod:`claude` already renders, so no
Codex-specific step/body format exists to diverge from.
"""

from __future__ import annotations

from narrativetrace_skills.render._body import (
    ResolveSnippet,
    common_frontmatter_lines,
    render_skill_page,
)
from narrativetrace_skills.skill import Skill


def render_codex_skill(skill: Skill, resolve_snippet: ResolveSnippet) -> str:
    return render_skill_page(skill, resolve_snippet, _render_frontmatter)


def _render_frontmatter(skill: Skill) -> str:
    return "\n".join(["---", *common_frontmatter_lines(skill), "---"])
