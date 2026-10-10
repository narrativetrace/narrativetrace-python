# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial pass (milestone 2): behaviour implemented but asserted by no other test.

CURATED. A cheap model generated 89 candidates over these modules; these are the ones that survived
reading. Coverage was already 100% statement and branch with a fault-path test per guard, so most
candidates were either duplicates of an existing case or assertions that cannot fail — an
`assert isinstance(result, bool)` on a function annotated ``-> bool``, an
``assert len(url) <= MAX_LENGTH`` that restates a postcondition, an
``assert "~" in body or body`` whose second disjunct is a non-empty string. The pass's real value
was one question it asked and declined to answer: CRLF, which turned out to be a genuine defect,
fixed and pinned in ``test_structural_trace.py``.

What is here is the behaviour that was genuinely unasserted: the label limit's exact boundary, the
encoded-run floor from BELOW, the renderer's own "not reported" fallback, and canonicalisation as a
normal form.
"""

from __future__ import annotations

import pytest
from reports import a_report

from narrativetrace_tooling.feedback.matchers import BASE64_RUN, shannon_bits_per_character
from narrativetrace_tooling.feedback.public_repository import labels_for
from narrativetrace_tooling.feedback.render import body
from narrativetrace_tooling.feedback.report import AgentIdentity, FeedbackCategory
from narrativetrace_tooling.feedback.rules import ENTROPY
from narrativetrace_tooling.feedback.vocabulary import canonical

_LABEL_LIMIT = 50
_LANG_PREFIX_LENGTH = len("lang:")


def _language_label(language: str) -> str:
    return next(label for label in labels_for(a_report(language=language)) if "lang:" in label)


class TestTheLabelLimitsExactBoundary:
    """The existing test clips a 200-character tag, which only proves clipping happens somewhere.
    These three say WHERE — one character either side of the platform's own limit."""

    @pytest.mark.parametrize("length", [_LABEL_LIMIT - 1, _LABEL_LIMIT], ids=["just-under", "at"])
    def test_a_label_inside_the_limit_is_left_alone(self, length: int) -> None:
        tag = "a" * (length - _LANG_PREFIX_LENGTH)

        label = _language_label(tag)

        assert label == f"lang:{tag}"
        assert len(label) == length

    def test_a_label_one_character_over_the_limit_loses_exactly_that_character(self) -> None:
        """Off by one here is a label the host refuses outright, which drops it silently for every
        reporter without push access — the failure mode nobody sees."""
        tag = "a" * (_LABEL_LIMIT + 1 - _LANG_PREFIX_LENGTH)

        label = _language_label(tag)

        assert len(label) == _LABEL_LIMIT
        assert label == f"lang:{tag[:-1]}"

    @pytest.mark.parametrize("category", list(FeedbackCategory), ids=lambda c: c.id)
    def test_no_label_of_any_category_can_exceed_the_limit(
        self, category: FeedbackCategory
    ) -> None:
        labels = labels_for(a_report(category=category, language="zh-Hans-CN-x-" + "a" * 60))

        assert all(len(label) <= _LABEL_LIMIT for label in labels)


class TestTheEncodedRunFloorFromBelow:
    """Every existing case approaches the 32-character floor from ABOVE, or uses a hex word far
    below it. One character short of the floor is the side that decides whether an ordinary
    identifier is a secret."""

    def test_a_dense_run_one_character_short_of_the_floor_is_filable(self) -> None:
        run = "Zm9vYmFyYmF6cXV1eHdhbGRvZnJlZG1p"[:31]

        assert len(run) == 31
        assert shannon_bits_per_character(run) > 4.0, "dense enough that only LENGTH saves it"
        assert BASE64_RUN.findall(run) == []
        assert not ENTROPY.rejects(run)

    def test_and_the_same_run_at_the_floor_is_not(self) -> None:
        """The pair is the point: one character apart, opposite verdicts, and the only difference
        is the floor."""
        run = "Zm9vYmFyYmF6cXV1eHdhbGRvZnJlZG1p"

        assert len(run) == 32
        assert ENTROPY.rejects(run)


class TestTheRenderersOwnFallbackForAnUnnamedAgent:
    """``AgentIdentity.describe()`` returning ``""`` is tested; what the BODY does with that empty
    string was not. An agent that will not name itself still gets to file, and the report has to say
    something a reader of the issue can act on."""

    def test_an_agent_that_did_not_name_itself_reads_as_not_reported(self) -> None:
        rendered = body(a_report(agent=AgentIdentity.unknown()))

        assert "- agent: not reported" in rendered
        assert "- agent: \n" not in rendered

    def test_a_product_with_no_model_is_the_whole_line(self) -> None:
        rendered = body(a_report(agent=AgentIdentity("example-cli", "")))

        assert "- agent: example-cli\n" in rendered

    def test_the_fallback_is_the_renderers_and_not_the_identitys(self) -> None:
        """Stated as the difference, so a later "fix" that moved the fallback into
        ``describe()`` would have to move this test too — and `describe()` returning a sentence
        would put it in the issue-form URL's ``agent`` parameter as well, where "not reported" is
        noise rather than information."""
        assert AgentIdentity.unknown().describe() == ""
        assert "not reported" in body(a_report(agent=AgentIdentity.unknown()))


class TestCanonicalIsANormalForm:
    def test_canonicalising_a_canonical_key_changes_nothing(self) -> None:
        """Idempotence, which is what lets the deny-list hold already-folded terms: if folding
        twice differed from folding once, every term in the vocabulary would have to be stored in
        whichever form the second pass produced."""
        once = canonical("Contraseña_Usuario")

        assert canonical(once) == once == "contrasena_usuario"

    def test_both_spellings_reach_the_same_normal_form(self) -> None:
        """A PAIR of spellings is written as escapes; a single one (above) may be a literal.
        The two forms render identically, so a pair written as literals is one nobody can
        check — and this assertion written that way is ``canonical(x) == canonical(x)``. It
        was, twice in this milestone, before both were escaped."""
        assert canonical("contrase\u00f1a") == canonical("contrasen\u0303a")
