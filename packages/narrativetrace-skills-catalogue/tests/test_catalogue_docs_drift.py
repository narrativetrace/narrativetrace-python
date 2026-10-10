# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Every catalogue skill is named on every public page that lists the skills: ``llms.txt``'s
"Agent skills" section, ``agent-skills.md`` and each of its translations. Mirrors Java's
``CatalogueDocsDriftTest``.

INTENT: the rendered pages and ``AGENTS.md`` are drift-checked against the catalogue by
``poe skills-check``, but these pages are written by hand; without this test a skill added to
``SKILLS`` ships with ``check`` green and no page telling a reader it exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from narrativetrace_skills.catalogue_index import SKILLS
from narrativetrace_skills.skill import Skill

_DOCS = next(p for p in Path(__file__).resolve().parents if (p / "uv.lock").is_file()) / (
    "documentation"
)

_SKILL_PAGES = (
    "agent-skills.md",
    "es/habilidades-del-agente.md",
    "pt-BR/habilidades-do-agente.md",
    "zh-CN/智能体技能.md",
)


def _llms_agent_skills_section() -> str:
    llms = (_DOCS / "llms.txt").read_text(encoding="utf-8")
    section = llms[llms.index("## Agent skills") :]
    return section[: section.index("\n## ", 1)]


@pytest.mark.parametrize("skill", SKILLS, ids=[s.canonical_name for s in SKILLS])
def test_llms_txt_lists_the_skill_in_its_agent_skills_section(skill: Skill) -> None:
    assert f"- `{skill.canonical_name}` — " in _llms_agent_skills_section()


@pytest.mark.parametrize("skill", SKILLS, ids=[s.canonical_name for s in SKILLS])
@pytest.mark.parametrize("page", _SKILL_PAGES)
def test_every_agent_skills_page_names_the_skill_in_its_list(skill: Skill, page: str) -> None:
    assert f"- **`{skill.canonical_name}`**" in (_DOCS / page).read_text(encoding="utf-8")


def test_llms_txt_counts_the_skills_it_lists() -> None:
    words = {6: "Six"}
    assert _llms_agent_skills_section().count("\n- `") == len(SKILLS)
    assert f"{words[len(SKILLS)]} skills ship with the packages." in _llms_agent_skills_section()
