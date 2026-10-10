# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Whether a page nobody stamped is nevertheless ours — the one comparison adoption rests on, and
every near miss that has to stay a refusal.

Named after the Java port's ``AdoptionTest`` so the two lists diff.
"""

from __future__ import annotations

from typing import Any

import pytest

from narrativetrace_tooling.init import adoption

PAGE = "---\nname: doctor\n---\n\nbody of doctor\n"

MISSING: Any = None


class TestAPageThatIsOurs:
    def test_the_carriers_own_page_is_adoptable(self) -> None:
        assert adoption.is_adoptable(PAGE, PAGE) is True

    def test_the_same_page_checked_out_with_crlf_is_adoptable(self) -> None:
        """A registry's pages come out of a git checkout, so the line ending is whatever the person
        who cloned the repository configured — it says nothing about whose page this is."""
        assert adoption.is_adoptable(PAGE.replace("\n", "\r\n"), PAGE) is True

    def test_a_carrier_rendering_with_crlf_is_adoptable_against_an_lf_checkout(self) -> None:
        assert adoption.is_adoptable(PAGE, PAGE.replace("\n", "\r\n")) is True

    def test_a_bare_carriage_return_checkout_is_adoptable_too(self) -> None:
        assert adoption.is_adoptable(PAGE.replace("\n", "\r"), PAGE) is True


class TestTheNearMisses:
    """Each one is somebody's edit or another release, and both are what the refusal protects."""

    def test_one_trailing_space_is_not_adoptable(self) -> None:
        assert adoption.is_adoptable(PAGE.replace("name: doctor", "name: doctor "), PAGE) is False

    def test_a_reordered_frontmatter_key_is_not_adoptable(self) -> None:
        reordered = "---\ndescription: d\nname: doctor\n---\n\nbody of doctor\n"
        original = "---\nname: doctor\ndescription: d\n---\n\nbody of doctor\n"

        assert adoption.is_adoptable(reordered, original) is False

    def test_a_lost_final_newline_is_not_adoptable(self) -> None:
        assert adoption.is_adoptable(PAGE.rstrip("\n"), PAGE) is False

    def test_another_releases_wording_is_not_adoptable(self) -> None:
        assert adoption.is_adoptable(PAGE.replace("body of", "the body of"), PAGE) is False

    def test_the_other_flavours_page_is_not_adoptable(self) -> None:
        vendor = "---\nname: doctor\nallowed-tools: Bash(uv *)\n---\n\nbody of doctor\n"

        assert adoption.is_adoptable(vendor, PAGE) is False

    def test_an_empty_installed_page_is_never_adoptable(self) -> None:
        """A skill directory with no page at all is a directory somebody else made, not a copy of
        ours — and adopting it would mean writing one where nothing was."""
        assert adoption.is_adoptable("", PAGE) is False

    def test_a_carrier_that_renders_nothing_adopts_nothing_either(self) -> None:
        assert adoption.is_adoptable("", "") is False


class TestGuards:
    def test_refuses_to_compare_a_page_that_is_not_there_at_all(self) -> None:
        """Anchored, not searched: ``pytest.raises(match=...)`` is ``re.search``, so an unanchored
        pattern passes against a message with anything wrapped around it — and a mutation run proved
        it by surviving a mutant that did exactly that."""
        anchored = r"\Aadoption compares two pages, never None\Z"

        with pytest.raises(TypeError, match=anchored):
            adoption.is_adoptable(MISSING, PAGE)
        with pytest.raises(TypeError, match=anchored):
            adoption.is_adoptable(PAGE, MISSING)
