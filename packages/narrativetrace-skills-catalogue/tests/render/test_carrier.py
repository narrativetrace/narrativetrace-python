# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from narrativetrace_skills.render.carrier import render_carrier_files
from narrativetrace_skills.render.catalogue_manifest import render_catalogue_manifest
from narrativetrace_skills.render.claude import render_claude_skill
from narrativetrace_skills.render.codex import render_codex_skill
from narrativetrace_skills.skill import Skill


def _skill(**overrides: object) -> Skill:
    base: dict[str, object] = {
        "canonical_name": "demo-skill",
        "skill_class": "mechanical",
        "description": "A demo skill.",
        "fixture": "examples/demo",
        "steps": (),
        "allowed_tools": ("uv", "git"),
    }
    base.update(overrides)
    return Skill(**base)  # type: ignore[arg-type]


def _resolve_snippet(path: str) -> str:
    return f"snippet:{path}"


class TestRenderCarrierFiles:
    def test_carries_the_catalogue_manifest_at_the_carrier_root(self) -> None:
        skills = (_skill(),)
        files = render_carrier_files(skills, _resolve_snippet)
        assert files["catalogue.json"] == render_catalogue_manifest(skills)

    def test_one_claude_and_one_agents_page_per_skill(self) -> None:
        skills = (_skill(canonical_name="a-skill"), _skill(canonical_name="b-skill"))
        files = render_carrier_files(skills, _resolve_snippet)
        assert set(files) == {
            "catalogue.json",
            "claude/a-skill/SKILL.md",
            "agents/a-skill/SKILL.md",
            "claude/b-skill/SKILL.md",
            "agents/b-skill/SKILL.md",
        }

    def test_claude_page_matches_the_claude_renderer(self) -> None:
        skill = _skill()
        files = render_carrier_files((skill,), _resolve_snippet)
        assert (
            files["claude/demo-skill/SKILL.md"]
            == f"{render_claude_skill(skill, _resolve_snippet)}\n"
        )

    def test_agents_page_matches_the_codex_renderer(self) -> None:
        skill = _skill()
        files = render_carrier_files((skill,), _resolve_snippet)
        assert (
            files["agents/demo-skill/SKILL.md"]
            == f"{render_codex_skill(skill, _resolve_snippet)}\n"
        )

    def test_empty_catalogue_renders_only_the_manifest(self) -> None:
        files = render_carrier_files((), _resolve_snippet)
        assert set(files) == {"catalogue.json"}
