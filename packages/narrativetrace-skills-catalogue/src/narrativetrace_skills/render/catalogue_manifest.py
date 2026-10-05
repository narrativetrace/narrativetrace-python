# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders ``catalogue.json``: the versionless manifest an installer reads to discover the
catalogue's skills without importing this (private) package -- shipped byte-identical in both the
published ``narrativetrace-skills`` carrier and ``narrativetrace``'s own bundled copy (Phase 3
milestone 1, D2). Deliberately versionless: the stamp comes from the carrier package's own
version at install time, never a value baked in here.
"""

from __future__ import annotations

import json

from narrativetrace_skills.skill import Skill


def render_catalogue_manifest(skills: tuple[Skill, ...]) -> str:
    payload = {
        "runtime": "python",
        "skills": [
            {
                "name": skill.canonical_name,
                "description": skill.description,
                "agents": f"agents/{skill.canonical_name}/SKILL.md",
                "claude": f"claude/{skill.canonical_name}/SKILL.md",
            }
            for skill in skills
        ],
    }
    return f"{json.dumps(payload, indent=2)}\n"
