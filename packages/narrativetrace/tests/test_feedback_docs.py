# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The prose a reader acts on when something is wrong must carry the verb's real spelling.

``documentation/llms.txt``'s "Report a problem" shows the command the ``narrativetrace-feedback``
skill runs, and both it and ``documentation/agent-skills.md`` name the repository the pre-filled
URL points at. None of that is a ``<!-- snippet: -->`` embed (the command is a catalogue constant
with placeholders, not a file), so this module is what makes it a listing that can drift and fail
rather than a sentence that was true once.

**@llmNote** The assertions are word for word. A "contains ``feedback``" check would stay green
under every rewording of the command, which is the failure it exists to catch.
"""

from __future__ import annotations

import re
from pathlib import Path

from narrativetrace_skills import SKILLS
from narrativetrace_skills.catalogue.feedback_commands import DRAFT_REPORT

from narrativetrace_tooling.feedback.public_repository import SLUG


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


_DOCUMENTATION = _repo_root() / "documentation"
LLMS_TXT = _DOCUMENTATION / "llms.txt"
AGENT_SKILLS = _DOCUMENTATION / "agent-skills.md"
"""THE declared inputs of this module: two named files, each read as a whole."""


def _report_a_problem_section() -> str:
    text = LLMS_TXT.read_text(encoding="utf-8")
    match = re.search(r"^## Report a problem\n(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL)
    assert match is not None, "llms.txt has no '## Report a problem' section"
    return match.group(1)


class TestLlmsTxtReportAProblem:
    def test_shows_the_exact_command_the_skill_runs_in_its_own_fence(self) -> None:
        assert f"```bash\n{DRAFT_REPORT}\n```" in _report_a_problem_section()

    def test_names_the_skill_and_the_public_repository_the_url_points_at(self) -> None:
        section = _report_a_problem_section()
        assert "`narrativetrace-feedback` skill" in section
        assert f"`github.com/{SLUG}`" in section

    def test_says_filing_is_public(self) -> None:
        assert "Filing is public: it shows that your project uses NarrativeTrace." in (
            _report_a_problem_section()
        )


class TestEverySkillIsListed:
    def test_llms_txt_lists_every_catalogue_skill_once(self) -> None:
        listed = re.findall(
            r"^- `([a-z-]+)` — ", LLMS_TXT.read_text(encoding="utf-8"), re.MULTILINE
        )
        assert sorted(listed) == sorted(skill.canonical_name for skill in SKILLS)

    def test_agent_skills_links_every_skills_rendered_pages_once_per_platform(self) -> None:
        text = AGENT_SKILLS.read_text(encoding="utf-8")
        for skill in SKILLS:
            assert text.count(f"/skills/{skill.canonical_name}/SKILL.md)") == 2, (
                skill.canonical_name
            )


class TestAgentSkillsNamesTheSameRepository:
    def test_the_verb_paragraph_names_the_repository_the_url_points_at(self) -> None:
        assert f"`github.com/{SLUG}`" in AGENT_SKILLS.read_text(encoding="utf-8")
