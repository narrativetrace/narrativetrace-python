# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders the whole file tree the skills carrier ships -- both the published
``narrativetrace-skills`` distribution's ``skills/`` directory and the byte-identical copy
``narrativetrace`` bundles as package data (Phase 3 milestone 1, D1/D2). One function so the two
targets can never drift from each other: each caller decides where to write these relative paths.
"""

from __future__ import annotations

from narrativetrace_skills.render._body import ResolveSnippet
from narrativetrace_skills.render.catalogue_manifest import render_catalogue_manifest
from narrativetrace_skills.render.claude import render_claude_skill
from narrativetrace_skills.render.codex import render_codex_skill
from narrativetrace_skills.skill import Skill


def render_carrier_files(
    skills: tuple[Skill, ...], resolve_snippet: ResolveSnippet
) -> dict[str, str]:
    files: dict[str, str] = {"catalogue.json": render_catalogue_manifest(skills)}
    for skill in skills:
        files[f"claude/{skill.canonical_name}/SKILL.md"] = (
            f"{render_claude_skill(skill, resolve_snippet)}\n"
        )
        files[f"agents/{skill.canonical_name}/SKILL.md"] = (
            f"{render_codex_skill(skill, resolve_snippet)}\n"
        )
    return files
