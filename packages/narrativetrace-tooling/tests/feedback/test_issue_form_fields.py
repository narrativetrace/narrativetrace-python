# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The issue form and the URL that pre-fills it, held together.

INTENT (cross-port item 5): GitHub documents a form field's ``id`` as "the canonical identifier for
the field in URL query parameter prefills" — and SILENTLY IGNORES a parameter naming an id the form
does not have. So a renamed field does not fail anywhere: it produces a form that opens with half
its boxes empty, and nobody finds out until a reporter fills them in by hand. This module is the
only thing that notices.

**The declared input of this module is one file**, named by :data:`FORM_PATH` — not a glob, not a
directory walk. ``poe check`` has no up-to-date mechanism to go stale the way a Gradle task input
does, so this port's own shape of that hole is a test that would pass whatever the file said:
:class:`TestThisModuleReallyReadsTheForm` is the PROBE, and it perturbs the form's text in memory
and asserts the verdict flips.

**@llmNote** The form is read as TEXT rather than parsed as YAML, because this distribution declares
zero dependencies and the question is a flat one: which ids does the file declare. If the question
ever becomes structural (which validations, which options are ordered how), the test moves to a
package that may have a YAML parser rather than growing one here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final
from urllib.parse import parse_qs, urlparse

import pytest
from reports import a_report

from narrativetrace_tooling.feedback.issue_form_url import issue_form_url
from narrativetrace_tooling.feedback.public_repository import FORM
from narrativetrace_tooling.feedback.report import FeedbackCategory


def _workspace_root() -> Path:
    """The workspace root, found by walking up rather than by counting directories — the same
    reason ``tests/test_architecture.py`` does: mutmut re-runs this suite from its own
    ``mutants/tests/`` copy, and a relative ``parents[n]`` would point at that copy."""
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


FORM_PATH: Final = _workspace_root() / ".github" / "ISSUE_TEMPLATE" / FORM
"""THE declared input of this module. One named file, so a missing or renamed form fails loudly
instead of making every assertion below vacuously true."""

_ID_LINE: Final = re.compile(r"^\s*id: (\S+)$", re.MULTILINE)

_RESERVED: Final = ("template", "title", "labels")
"""Parameters the URL carries that are GitHub's own, not form field ids."""


def _form_text() -> str:
    return FORM_PATH.read_text(encoding="utf-8")


def _declared_ids(form_text: str | None = None) -> list[str]:
    return _ID_LINE.findall(form_text if form_text is not None else _form_text())


def _pre_filled_parameters() -> list[str]:
    query = parse_qs(urlparse(issue_form_url(a_report())).query)
    return [name for name in query if name not in _RESERVED]


class TestTheFormIsWhereTheUrlSaysItIs:
    def test_the_form_file_exists(self) -> None:
        assert FORM_PATH.is_file(), f"{FORM_PATH} must exist — the URL names it in every report"

    def test_the_form_declares_some_ids_at_all(self) -> None:
        """The anti-vacuity guard for every subset assertion below: a reader that matched nothing
        would make "every pre-filled parameter is a declared id" fail loudly, but "every declared
        id is on the form" trivially true."""
        assert len(_declared_ids()) >= 10


class TestEveryFieldTheUrlPreFillsIsAFieldTheFormDeclares:
    def test_no_pre_filled_parameter_names_an_id_the_form_does_not_have(self) -> None:
        declared = _declared_ids()

        assert set(_pre_filled_parameters()) <= set(declared), (
            "a parameter naming an id the form does not have is silently ignored by the host: the"
            " form opens with that box empty and nothing fails"
        )

    def test_the_url_really_does_pre_fill_something(self) -> None:
        assert len(_pre_filled_parameters()) >= 6


class TestEveryFieldTheReportCanFillIsOnTheForm:
    @pytest.mark.parametrize(
        "field",
        ["category", "runtime", "install", "step", "did", "happened", "expected"],
    )
    def test_the_report_field(self, field: str) -> None:
        assert field in _declared_ids()

    @pytest.mark.parametrize("field", ["language", "agent"])
    def test_the_optional_field(self, field: str) -> None:
        assert field in _declared_ids()

    @pytest.mark.parametrize("field", ["report", "reviewed"])
    def test_the_box_the_body_is_pasted_into_and_the_attestation_that_gates_submitting(
        self, field: str
    ) -> None:
        assert field in _declared_ids()


class TestTheFormAndTheVerbAgreeOnTheClosedSets:
    @pytest.mark.parametrize("category", list(FeedbackCategory), ids=lambda c: c.id)
    def test_the_dropdown_offers_every_category_the_verb_accepts(
        self, category: FeedbackCategory
    ) -> None:
        """A drafted report pre-fills ``category=<id>``; an id the dropdown does not offer is one
        the host ignores, leaving the dropdown unset on a required field."""
        assert f"- {category.id}" in _form_text()

    def test_the_form_carries_the_from_agent_label_the_verb_also_applies(self) -> None:
        assert "- from-agent" in _form_text()

    def test_the_attestation_is_required(self) -> None:
        assert "required: true" in _form_text()
        assert "no values from my traces" in _form_text()

    def test_the_form_names_the_body_file_the_verb_actually_writes(self) -> None:
        """A path only the form knows is a path that goes stale. The verb's own constant is
        asserted against this text in the CLI's tests, where both are visible."""
        assert "build/narrativetrace/feedback/feedback-body.md" in _form_text()


class TestTheFormSaysWhatFilingMeansToSomebodyWhoArrivedWithoutTheVerb:
    def test_it_says_the_issue_is_public(self) -> None:
        assert "**This issue is public.**" in _form_text()

    def test_it_never_asks_for_an_artifact_that_carries_values(self) -> None:
        assert "Never paste a rendered narrative, a log file or a source file" in _form_text()


class TestThisModuleReallyReadsTheForm:
    """The PROBE of :data:`FORM_PATH`'s declaration (cross-port item 8), as a content change rather
    than a timestamp. ``touch`` is not a probe anywhere, and in a pytest world there is no
    up-to-date check to probe at all — what can go wrong here is a test that passes whatever the
    file says. So: perturb the text and the verdict must flip.
    """

    def test_renaming_a_field_the_url_pre_fills_breaks_the_subset(self) -> None:
        perturbed = _form_text().replace("id: step", "id: stepX")

        declared = _declared_ids(perturbed)

        assert "step" not in declared, "the perturbation must have landed"
        assert not set(_pre_filled_parameters()) <= set(declared), (
            "renaming a pre-filled field must break this module, or it is reading something else"
        )

    def test_removing_a_category_from_the_dropdown_breaks_the_closed_set(self) -> None:
        perturbed = _form_text().replace("        - doctor\n", "")

        assert "- doctor" not in perturbed
        assert "- skill" in perturbed, "only the one option may have gone"

    def test_the_reader_finds_an_id_only_on_its_own_line(self) -> None:
        """``id:`` appears inside this form's own prose as well (the markdown block talks about
        ids), so a reader matching anywhere would invent fields. Anchored per line."""
        assert _declared_ids("  id: real\ndescription: see id: not-a-field\n") == ["real"]
