# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

import json

from narrativetrace_skills.render.catalogue_manifest import render_catalogue_manifest
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


class TestRenderCatalogueManifest:
    def test_is_well_formed_json_ending_in_a_newline(self) -> None:
        rendered = render_catalogue_manifest((_skill(),))
        assert rendered.endswith("\n")
        json.loads(rendered)

    def test_runtime_is_python(self) -> None:
        payload = json.loads(render_catalogue_manifest((_skill(),)))
        assert payload["runtime"] == "python"

    def test_carries_no_version_field(self) -> None:
        payload = json.loads(render_catalogue_manifest((_skill(),)))
        assert "version" not in payload

    def test_one_entry_per_skill_with_the_four_fields(self) -> None:
        payload = json.loads(
            render_catalogue_manifest(
                (
                    _skill(canonical_name="narrativetrace-doctor", description="Diagnoses."),
                    _skill(canonical_name="add-narrative-tracing", description="Installs."),
                )
            )
        )
        assert payload["skills"] == [
            {
                "name": "narrativetrace-doctor",
                "description": "Diagnoses.",
                "agents": "agents/narrativetrace-doctor/SKILL.md",
                "claude": "claude/narrativetrace-doctor/SKILL.md",
            },
            {
                "name": "add-narrative-tracing",
                "description": "Installs.",
                "agents": "agents/add-narrative-tracing/SKILL.md",
                "claude": "claude/add-narrative-tracing/SKILL.md",
            },
        ]

    def test_skill_order_follows_the_input_order(self) -> None:
        payload = json.loads(
            render_catalogue_manifest(
                (
                    _skill(canonical_name="b-skill"),
                    _skill(canonical_name="a-skill"),
                )
            )
        )
        assert [entry["name"] for entry in payload["skills"]] == ["b-skill", "a-skill"]

    def test_empty_catalogue_renders_an_empty_skills_list(self) -> None:
        payload = json.loads(render_catalogue_manifest(()))
        assert payload == {"runtime": "python", "skills": []}
