# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The carrier index is read once, at open time, and every later stage treats it as a fact. These
cases run the reader against the REAL checked-in ``catalogue.json`` as well as against hand-written
malformed ones: a reader that only ever sees its own fixtures proves nothing about the file that
ships.

Named after the Java port's ``CatalogueReaderTest`` so the two lists diff. Java's
``JsonReaderTest`` has no counterpart: it exists because the JDK has no JSON reader, while
:mod:`json` is in Python's standard library — so the document-level refusals below go through
:func:`json.loads`, and everything Java's own reader rejected about a *catalogue* (a missing
field, a field of the wrong type, a repeated name) is still rejected here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from narrativetrace_tooling.init.catalogue import (
    SkillCatalogue,
    SkillEntry,
    SkillFlavour,
    read_catalogue,
)

DOCTOR = """
      {"name": "narrativetrace-doctor", "description": "Diagnoses an install.",
       "agents": "agents/narrativetrace-doctor/SKILL.md",
       "claude": "claude/narrativetrace-doctor/SKILL.md"}
"""


def _repo_root() -> Path:
    """The workspace root, found by walking up rather than by counting directories — the same
    reason ``test_distribution_licensing.py`` gives: mutmut runs this suite from a ``mutants/``
    copy one level deeper, where a fixed ``parents[n]`` resolves somewhere else entirely."""
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


REAL_CATALOGUE = _repo_root() / "packages" / "narrativetrace-skills" / "skills" / "catalogue.json"


def catalogue(skills: str) -> str:
    return '{"runtime": "python", "skills": [' + skills + "]}"


class TestReadCatalogue:
    def test_reads_the_runtime_and_one_skill_from_a_catalogue(self) -> None:
        read = read_catalogue(catalogue(DOCTOR))

        assert read.runtime == "python"
        assert read.skills == (
            SkillEntry(
                "narrativetrace-doctor",
                "Diagnoses an install.",
                "agents/narrativetrace-doctor/SKILL.md",
                "claude/narrativetrace-doctor/SKILL.md",
            ),
        )

    def test_reads_the_real_checked_in_catalogue(self) -> None:
        read = read_catalogue(REAL_CATALOGUE.read_text(encoding="utf-8"))

        names = [skill.name for skill in read.skills]
        assert read.runtime == "python"
        assert len(names) == len(set(names)) == 6
        for skill in read.skills:
            assert skill.agents_path == f"agents/{skill.name}/SKILL.md"
            assert skill.claude_path == f"claude/{skill.name}/SKILL.md"
            assert skill.description.strip()

    def test_finds_a_skill_by_name_and_reports_an_unknown_one_as_none(self) -> None:
        read = read_catalogue(catalogue(DOCTOR))

        assert read.skill("narrativetrace-doctor") is not None
        assert read.skill("narrativetrace-doctorx") is None

    def test_keeps_the_catalogue_order_of_two_skills(self) -> None:
        second = DOCTOR.replace("narrativetrace-doctor", "add-narrative-tracing")

        read = read_catalogue(catalogue(DOCTOR + "," + second))

        assert [skill.name for skill in read.skills] == [
            "narrativetrace-doctor",
            "add-narrative-tracing",
        ]


class TestARefusedCatalogue:
    """A malformed carrier is refused before any plan exists, with a message naming the entry —
    which is what makes a broken carrier impossible to half-install."""

    def test_refuses_a_catalogue_that_names_the_same_skill_twice(self) -> None:
        with pytest.raises(ValueError, match=r"names a skill twice.*narrativetrace-doctor"):
            read_catalogue(catalogue(DOCTOR + "," + DOCTOR))

    def test_refuses_a_skill_missing_a_flavour_path_and_names_it(self) -> None:
        no_claude = """
            {"name": "add-narrative-tracing", "description": "d", "agents": "agents/a/SKILL.md"}
        """

        with pytest.raises(ValueError, match=r'add-narrative-tracing has no "claude" string field'):
            read_catalogue(catalogue(no_claude))

    def test_refuses_a_skill_whose_name_is_not_a_string(self) -> None:
        with pytest.raises(ValueError, match=r'skill has no "name" string field'):
            read_catalogue(catalogue('{"name": {}}'))

    def test_refuses_a_skill_whose_description_is_a_number(self) -> None:
        """Python's :func:`json.loads` accepts a JSON number where Java's own reader refused the
        document outright. The typed field check is what refuses it here — so a catalogue that
        reads ``"description": 7`` is rejected in both ports, for different reasons."""
        numeric = '{"name": "n", "description": 7, "agents": "a", "claude": "c"}'

        with pytest.raises(ValueError, match=r'n has no "description" string field'):
            read_catalogue(catalogue(numeric))

    def test_refuses_a_skill_that_is_not_an_object(self) -> None:
        with pytest.raises(ValueError, match=r"skill must be a JSON object"):
            read_catalogue(catalogue('"narrativetrace-doctor"'))

    def test_refuses_a_catalogue_without_a_skills_array(self) -> None:
        with pytest.raises(ValueError, match=r'"skills" must be a JSON array'):
            read_catalogue('{"runtime": "python"}')

    def test_refuses_a_catalogue_without_a_runtime(self) -> None:
        with pytest.raises(ValueError, match=r'catalogue has no "runtime" string field'):
            read_catalogue('{"skills": []}')

    def test_refuses_a_catalogue_that_carries_no_skill_at_all(self) -> None:
        with pytest.raises(ValueError, match=r"at least one skill"):
            read_catalogue('{"runtime": "python", "skills": []}')

    def test_refuses_a_catalogue_that_is_not_an_object_at_all(self) -> None:
        with pytest.raises(ValueError, match=r"catalogue must be a JSON object"):
            read_catalogue("[]")

    def test_refuses_a_skill_whose_description_is_blank(self) -> None:
        blank = '{"name": "n", "description": "  ", "agents": "a", "claude": "c"}'

        with pytest.raises(ValueError, match=r"description must not be blank"):
            read_catalogue(catalogue(blank))

    def test_refuses_a_document_that_is_not_json_naming_where_reading_stopped(self) -> None:
        """The message says "malformed JSON", as the Java port's does, because the carrier reader
        quotes it into a refusal a person reads with no stack trace in front of them."""
        with pytest.raises(ValueError, match=r"malformed JSON at offset 11:"):
            read_catalogue('{"runtime":')

    def test_refuses_no_document_at_all(self) -> None:
        with pytest.raises(ValueError, match=r"\Ano JSON text to read\Z"):
            read_catalogue(None)  # type: ignore[arg-type]


class TestSkillCatalogue:
    def test_refuses_a_catalogue_built_without_a_skill_list(self) -> None:
        with pytest.raises(ValueError, match=r"at least one skill"):
            SkillCatalogue("python", ())

    def test_refuses_a_catalogue_built_with_a_blank_runtime(self) -> None:
        with pytest.raises(ValueError, match=r"runtime must not be blank"):
            SkillCatalogue(" ", (_entry("n"),))

    def test_holds_its_skills_as_a_tuple_nothing_can_append_to(self) -> None:
        read = read_catalogue(catalogue(DOCTOR))

        assert isinstance(read.skills, tuple)
        with pytest.raises(AttributeError):
            read.skills.append(_entry("another"))  # type: ignore[attr-defined]


class TestSkillEntry:
    def test_each_flavour_picks_its_own_path(self) -> None:
        entry = _entry("n")

        assert entry.path_for(SkillFlavour.AGENTS) == "agents/n/SKILL.md"
        assert entry.path_for(SkillFlavour.CLAUDE) == "claude/n/SKILL.md"

    def test_refuses_a_path_for_no_flavour(self) -> None:
        with pytest.raises(ValueError, match=r"a flavour must be given"):
            _entry("n").path_for(None)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        ("field", "what"),
        [(0, "name"), (1, "description"), (2, "agents path"), (3, "claude path")],
    )
    def test_refuses_a_blank_field_naming_which_one(self, field: int, what: str) -> None:
        values = ["n", "d", "agents/n/SKILL.md", "claude/n/SKILL.md"]
        values[field] = " "

        with pytest.raises(ValueError, match=rf"{re.escape(what)} must not be blank"):
            SkillEntry(*values)


class TestSkillFlavour:
    def test_each_flavour_knows_where_it_installs(self) -> None:
        assert SkillFlavour.AGENTS.install_root == ".agents/skills"
        assert SkillFlavour.CLAUDE.install_root == ".claude/skills"

    def test_the_two_flavours_are_the_whole_of_it_in_install_order(self) -> None:
        """The open standard first: it is written into every project, and the vendor flavour only
        where a vendor is detected. Every loop over the flavours relies on that order."""
        assert list(SkillFlavour) == [SkillFlavour.AGENTS, SkillFlavour.CLAUDE]

    def test_each_flavours_value_is_the_catalogue_field_that_carries_its_path(self) -> None:
        assert SkillFlavour.AGENTS.value == "agents"
        assert SkillFlavour.CLAUDE.value == "claude"


def _entry(name: str) -> SkillEntry:
    return SkillEntry(name, "What it does.", f"agents/{name}/SKILL.md", f"claude/{name}/SKILL.md")
