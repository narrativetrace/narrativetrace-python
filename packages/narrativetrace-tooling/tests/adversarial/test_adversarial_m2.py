# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The adversarial pass over Phase 4 milestone 2 (CLAUDE.md): cases nothing else covers.

Written by a cheap model against the finished code, then read case by case and curated. What
survived is what adds coverage the hand-written suites do not have — unusual page content,
line-ending and byte-order-mark combinations, the construction guards reached with the wrong TYPE
rather than with ``None``, and skill names nobody would choose on purpose. What was dropped restated
a case already pinned in ``tests/init/``, or asserted something unrelated to its own name.

ONE finding was a real defect and is kept here INVERTED, beside the guard it caused:
``AdoptPage`` accepted an empty ``after``, so an "adoption" could empty the very page it claimed to
be taking nothing from. The generated test documented that as acceptable ("though this would be
strange"); it is not, and ``action.py`` now refuses it the way ``ReplaceLink`` already refused its
own empty page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from narrativetrace_tooling.init import adoption
from narrativetrace_tooling.init.action import AdoptPage, ReplaceLink
from narrativetrace_tooling.init.catalogue import SkillFlavour
from narrativetrace_tooling.init.project_state import InstalledSkill, Presence, ProjectState

MISSING: Any = None

LINK = Path(".agents/skills/doctor")

PAGE_UNDER_LINK = Path(".agents/skills/doctor/SKILL.md")


def foreign(name: str) -> InstalledSkill:
    return InstalledSkill(SkillFlavour.AGENTS, name, Presence.FOREIGN, body="page\n")


class TestAdoptionWithUnusualContent:
    """Pages whose SHAPE is unlike a rendered skill page, which the comparison must not mind."""

    def test_a_page_that_is_only_a_frontmatter_block_is_adoptable(self) -> None:
        page = "---\nname: doctor\n---\n"

        assert adoption.is_adoptable(page, page) is True

    def test_a_page_without_any_frontmatter_is_adoptable(self) -> None:
        page = "just some text\n"

        assert adoption.is_adoptable(page, page) is True

    def test_a_one_byte_page_is_adoptable_and_a_one_byte_difference_is_not(self) -> None:
        assert adoption.is_adoptable("x", "x") is True
        assert adoption.is_adoptable("x", "y") is False

    def test_a_page_of_only_newlines_is_content_and_an_empty_one_is_not(self) -> None:
        """Whitespace is content: the comparison is bytes, and a page of blank lines on disk is a
        page somebody's tool wrote."""
        assert adoption.is_adoptable("\n\n\n", "\n\n\n") is True
        assert adoption.is_adoptable("", "has content\n") is False
        assert adoption.is_adoptable("has content\n", "") is False

    def test_one_byte_in_a_megabyte_still_disqualifies_adoption(self) -> None:
        """The comparison is exact at any size — no sampling, no hashing shortcut."""
        large = "x" * 1_000_000 + "\n"
        almost = large[:-2] + "y\n"

        assert adoption.is_adoptable(large, large) is True
        assert adoption.is_adoptable(large, almost) is False


class TestAdoptionAcrossLineEndingsAndByteOrderMarks:
    """What a git checkout can legitimately change, and what it cannot."""

    def test_a_page_with_mixed_line_endings_is_adoptable_against_a_uniform_one(self) -> None:
        """A tree checked out with mixed endings — a real state after a partial `.gitattributes`
        change — is still this carrier's page."""
        assert adoption.is_adoptable("a\nb\r\nc\n", "a\nb\nc\n") is True

    def test_adoption_is_symmetric_across_the_two_spellings(self) -> None:
        assert adoption.is_adoptable("a\r\nb\r\n", "a\nb\n") is True
        assert adoption.is_adoptable("a\nb\n", "a\r\nb\r\n") is True

    def test_a_bare_carriage_return_checkout_is_adoptable(self) -> None:
        assert adoption.is_adoptable("a\rb\r", "a\nb\n") is True

    def test_a_byte_order_mark_on_one_side_only_is_a_real_difference(self) -> None:
        """A BOM is a byte somebody's editor added, not a line ending — so it is not forgiven."""
        plain = "content\n"
        with_mark = "﻿content\n"

        assert adoption.is_adoptable(with_mark, plain) is False
        assert adoption.is_adoptable(plain, with_mark) is False
        assert adoption.is_adoptable(with_mark, with_mark) is True

    def test_a_trailing_space_is_not_a_line_ending_and_is_not_forgiven(self) -> None:
        assert adoption.is_adoptable("line1 \n", "line1\n") is False


class TestAdoptionsGuardReachedWithTheWrongType:
    """The guard says "never None", and the hand-written suite passes ``None``. Every other
    non-string reaches the same guard, which is what ``isinstance`` is there for."""

    @pytest.mark.parametrize("wrong", [42, ["a", "list"], {"a": "dict"}, b"bytes", 0.5])
    def test_a_non_string_page_is_refused_whichever_side_it_is_on(self, wrong: Any) -> None:
        anchored = r"\Aadoption compares two pages, never None\Z"

        with pytest.raises(TypeError, match=anchored):
            adoption.is_adoptable(wrong, "page\n")
        with pytest.raises(TypeError, match=anchored):
            adoption.is_adoptable("page\n", wrong)


class TestAdoptingAPageMustNeverEmptyIt:
    """The one real finding of this pass, kept beside the guard it caused.

    The generated test asserted that ``AdoptPage`` accepts an empty ``after`` and called it
    "strange" but acceptable. It is not acceptable: adoption's whole promise is that nothing of
    anybody's is overwritten, and an action writing ``""`` over the page would break exactly that
    promise while the plan, the diff and the report all said "adopted". ``ReplaceLink`` already
    refused its own empty page for the same reason; ``AdoptPage`` now does too.
    """

    def test_refuses_to_adopt_a_page_by_emptying_it(self) -> None:
        with pytest.raises(ValueError, match=r"\Aa page is adopted by stamping it"):
            AdoptPage(PAGE_UNDER_LINK, "page\n", "")

    def test_still_refuses_an_adoption_where_there_was_no_page(self) -> None:
        with pytest.raises(ValueError, match=r"\Athere is nothing to adopt"):
            AdoptPage(PAGE_UNDER_LINK, "", "stamped\n")

    def test_a_page_of_only_whitespace_is_a_page_and_may_be_adopted(self) -> None:
        """Not symmetrical with the guard above on purpose: ``before`` is what is ON DISK, and a
        file holding three spaces is a file. ``after`` is what WE write, and we write no empty."""
        assert AdoptPage(PAGE_UNDER_LINK, "   ", "stamped\n").before == "   "


class TestWhereAReplacedLinksPageMaySit:
    """``page`` must be behind ``link``, after normalisation, or the plan would delete one path and
    write another and the diff would describe neither."""

    def test_a_page_directly_inside_the_link_is_accepted(self) -> None:
        assert ReplaceLink(LINK, PAGE_UNDER_LINK, "../x", "page\n").path == PAGE_UNDER_LINK

    def test_a_page_several_levels_below_the_link_is_accepted(self) -> None:
        deep = Path(".agents/skills/doctor/sub/dir/SKILL.md")

        assert ReplaceLink(LINK, deep, "../x", "page\n").path == deep

    def test_a_sibling_of_the_link_is_refused(self) -> None:
        with pytest.raises(ValueError, match=r"is not behind the link"):
            ReplaceLink(LINK, Path(".agents/skills/other/SKILL.md"), "../x", "page\n")

    def test_a_page_that_only_looks_nested_before_normalisation_is_refused(self) -> None:
        """``.agents/../.claude/...`` normalises OUT of the link, and the check runs after."""
        with pytest.raises(ValueError, match=r"is not behind the link"):
            ReplaceLink(LINK, Path(".agents/../.claude/skills/doctor/SKILL.md"), "../x", "page\n")

    @pytest.mark.parametrize("blank", ["", "   \n\t  "])
    def test_a_link_with_nothing_to_say_about_its_target_is_refused(self, blank: str) -> None:
        with pytest.raises(ValueError, match=r"\Areplacing a link names what it pointed at\Z"):
            ReplaceLink(LINK, PAGE_UNDER_LINK, blank, "page\n")

    @pytest.mark.parametrize("target", ["/absolute/path/to/target", "../../elsewhere", "x"])
    def test_a_target_is_kept_exactly_as_the_filesystem_reports_it(self, target: str) -> None:
        """Absolute, relative or a single character: the target exists to be PRINTED in a refusal or
        a replacement line, so nothing here parses or resolves it."""
        assert ReplaceLink(LINK, PAGE_UNDER_LINK, target, "page\n").target == target


class TestBothInstallRootsLinkedAtOnce:
    """Nothing in the hand-written suite links both flavours in one project."""

    def test_each_flavours_target_is_reported_independently(self) -> None:
        state = ProjectState(
            linked_install_roots={
                SkillFlavour.AGENTS: "../../shared/agents",
                SkillFlavour.CLAUDE: "../../shared/claude",
            }
        )

        assert state.linked_install_root(SkillFlavour.AGENTS) == "../../shared/agents"
        assert state.linked_install_root(SkillFlavour.CLAUDE) == "../../shared/claude"

    def test_no_skill_may_be_listed_under_either_of_them(self) -> None:
        """The invariant holds per flavour, so linking both forbids listing anything at all."""
        for flavour in SkillFlavour:
            with pytest.raises(AssertionError):
                ProjectState(
                    linked_install_roots={
                        SkillFlavour.AGENTS: "../../shared/agents",
                        SkillFlavour.CLAUDE: "../../shared/claude",
                    },
                    installed_skills=(
                        InstalledSkill(flavour, "doctor", Presence.FOREIGN, body="page\n"),
                    ),
                )

    def test_one_linked_root_still_allows_the_other_flavours_skills(self) -> None:
        state = ProjectState(
            linked_install_roots={SkillFlavour.AGENTS: "../../agents"},
            installed_skills=(
                InstalledSkill(SkillFlavour.CLAUDE, "doctor", Presence.FOREIGN, body="page\n"),
            ),
        )

        assert state.linked_install_root(SkillFlavour.AGENTS) == "../../agents"
        assert state.installed_skill(SkillFlavour.CLAUDE, "doctor") is not None


class TestSkillNamesNobodyWouldChooseOnPurpose:
    """A skill name is a directory name a registry chose, not one this catalogue did, so the
    installer has to carry whatever is there into the paths it names."""

    @pytest.mark.parametrize(
        "name", ["skill.with.dots", "skill with spaces", "a" * 200, "UPPER", "-leading-dash"]
    )
    def test_the_name_survives_into_both_paths_unchanged(self, name: str) -> None:
        skill = foreign(name)

        assert skill.directory == Path(".agents/skills") / name
        assert skill.page == Path(".agents/skills") / name / "SKILL.md"

    def test_a_name_that_is_only_whitespace_or_empty_is_refused(self) -> None:
        for blank in ("", "   "):
            with pytest.raises(
                ValueError, match=r"\Aan installed skill's name must not be blank\Z"
            ):
                InstalledSkill(SkillFlavour.AGENTS, blank, Presence.FOREIGN, body="page\n")
