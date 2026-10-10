# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The two channels a report may be filed through: the pre-filled issue-form URL, and the exact
``gh issue create`` line — printed, never run.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from reports import a_report

from narrativetrace_tooling.feedback.gh_command_line import gh_command_line
from narrativetrace_tooling.feedback.issue_form_url import (
    MAX_LENGTH,
    TRUNCATION_MARKER,
    issue_form_url,
)
from narrativetrace_tooling.feedback.public_repository import FORM, RUNTIME, SLUG, labels_for
from narrativetrace_tooling.feedback.report import AgentIdentity, FeedbackCategory

_BODY_FILE = "build/narrativetrace/feedback/feedback-body.md"


def _query(**overrides: object) -> dict[str, list[str]]:
    return parse_qs(urlparse(issue_form_url(a_report(**overrides))).query)


class TestWhereAPythonReportIsFiled:
    def test_the_repository_is_this_runtimes_own_public_one(self) -> None:
        assert SLUG == "narrativetrace/narrativetrace-python"

    def test_the_form_file_name_is_the_one_every_runtime_carries(self) -> None:
        """The form is a cross-runtime artifact; the repository is not. A different file name here
        would make the family's URL template per-runtime for no reason."""
        assert FORM == "narrativetrace-report.yml"

    def test_the_runtime_id_is_the_one_the_label_carries(self) -> None:
        assert RUNTIME == "python"

    def test_a_report_from_another_runtime_is_refused_rather_than_misfiled(self) -> None:
        """A wrong answer here is unfixable in public: a report filed into this tracker from
        another runtime's project is a public issue in the wrong repository, and deleting it does
        not un-publish it."""
        with pytest.raises(ValueError, match=r"runtime is 'typescript'"):
            issue_form_url(a_report(runtime="typescript"))
        with pytest.raises(ValueError, match=r"runtime is 'typescript'"):
            gh_command_line(a_report(runtime="typescript"), _BODY_FILE)


class TestTheLabelsTriageSortsOn:
    def test_the_four_label_families_in_a_stable_order(self) -> None:
        assert labels_for(a_report()) == (
            "from-agent",
            "runtime:python",
            "category:doctor",
            "lang:en",
        )

    def test_a_label_is_clipped_to_the_hosts_own_limit(self) -> None:
        """A label built past 50 characters is one GitHub refuses, so building it is never the
        right answer — and an unbounded label is also how a long language tag blew a URL's own
        length budget from inside the one parameter nothing clipped."""
        labels = labels_for(a_report(language="x" * 200))

        assert all(len(label) <= 50 for label in labels)
        assert labels[3].startswith("lang:xxx")

    def test_there_is_no_agent_label(self) -> None:
        """The agent product is free text as the agent reported it, so a label built from it is a
        label set strangers extend — and labels from a reporter without push access are silently
        dropped anyway. The agent line travels as a FIELD, where it is searchable and harmless."""
        assert not any(label.startswith("agent:") for label in labels_for(a_report()))


class TestTheIssueFormUrl:
    def test_it_points_at_the_new_issue_form_in_the_right_repository(self) -> None:
        parsed = urlparse(issue_form_url(a_report()))

        assert parsed.scheme == "https"
        assert parsed.netloc == "github.com"
        assert parsed.path == f"/{SLUG}/issues/new"

    def test_it_names_the_template_the_form_file_is(self) -> None:
        assert _query()["template"] == [FORM]

    def test_it_carries_the_short_searchable_fields(self) -> None:
        query = _query()

        assert query["runtime"] == ["python"]
        assert query["category"] == ["doctor"]
        assert query["step"] == ["trap.redaction-proof"]
        assert query["language"] == ["en"]
        assert query["agent"] == ["example-cli / example-model"]
        assert query["install"] == ["narrativetrace==0.2.0, narrativetrace-pytest==0.2.0"]

    def test_the_title_is_the_category_and_the_step(self) -> None:
        assert _query()["title"] == ["doctor: trap.redaction-proof"]

    def test_the_body_never_travels_in_the_url(self) -> None:
        """A doctor report and a structural trace are kilobytes, a URL that is too long answers
        414, and the limit is undocumented. The long fields live in the body file and the user
        pastes them."""
        query = _query()

        assert "report" not in query
        assert "did" not in query
        assert "doctor report" not in query

    def test_a_space_is_percent_encoded_rather_than_written_as_a_plus(self) -> None:
        """``urlencode`` implements HTML form encoding, where a space is ``+``; that is right
        inside a form POST and wrong inside a query the host's prefill reader hands to a form,
        which would show the plus signs."""
        url = issue_form_url(a_report(step="skill step 2"))

        assert "step=skill%20step%202" in url
        assert "+" not in urlparse(url).query

    def test_the_url_stays_inside_its_own_measured_budget(self) -> None:
        """The host answers 414 past an undocumented limit, so the budget is a conservative one we
        set ourselves and measure, rather than one a user discovers for us."""
        enormous = issue_form_url(
            a_report(
                install="narrativetrace==0.2.0, " * 400,
                step="t" * 2_000,
                agent=AgentIdentity("p" * 2_000, "m" * 2_000),
            )
        )

        assert len(enormous) <= MAX_LENGTH

    def test_a_field_that_did_not_fit_says_where_the_rest_is(self) -> None:
        url = issue_form_url(a_report(step="t" * 2_000))

        assert TRUNCATION_MARKER.strip() in parse_qs(urlparse(url).query)["step"][0]

    def test_a_short_report_is_not_clipped_at_all(self) -> None:
        assert TRUNCATION_MARKER.strip() not in issue_form_url(a_report())

    def test_the_per_field_ceiling_is_halved_until_the_whole_url_fits(self) -> None:
        """The loop, reached. Percent-encoding is what gets a URL past the budget even with every
        field already clipped to 400: one CJK character is three bytes and nine encoded
        characters, so 400 of them is 3,600 — and the step travels twice, in ``step`` and in the
        title. Clipping per field is not enough on its own; halving is."""
        wide = "\u5bc6" * 400

        url = issue_form_url(a_report(step=wide))

        assert len(url) <= MAX_LENGTH
        clipped = parse_qs(urlparse(url).query)["step"][0]
        assert len(clipped) < 400, "the ceiling must have come down, not just been applied"
        assert TRUNCATION_MARKER.strip() in clipped


class TestTheGhCommandLine:
    def test_it_is_the_exact_invocation_and_names_the_body_file(self) -> None:
        line = gh_command_line(a_report(), _BODY_FILE)

        assert line.startswith(f"gh issue create --repo {SLUG} --template {FORM} ")
        assert f"--body-file {_BODY_FILE}" in line

    def test_it_carries_the_title_and_every_label(self) -> None:
        line = gh_command_line(a_report(), _BODY_FILE)

        assert "--title 'doctor: trap.redaction-proof'" in line
        for label in labels_for(a_report()):
            assert f"--label {label}" in line

    def test_the_title_is_single_quoted_so_a_shell_interprets_nothing(self) -> None:
        """The step comes from a project — a test name, a check id, whatever the agent read — and
        an unquoted title containing ``;`` is a second command in a line we told somebody to paste
        into their shell."""
        line = gh_command_line(a_report(step="x; rm -rf /"), _BODY_FILE)

        assert "--title 'doctor: x; rm -rf /'" in line

    def test_a_quote_inside_the_title_cannot_end_the_quoting(self) -> None:
        line = gh_command_line(a_report(step="it's broken"), _BODY_FILE)

        assert "--title 'doctor: it'\\''s broken'" in line

    def test_a_printed_command_is_one_line(self) -> None:
        """A newline inside it would be a second command."""
        line = gh_command_line(a_report(step="first\nsecond"), _BODY_FILE)

        assert "\n" not in line
        assert "--title 'doctor: first second'" in line

    def test_there_is_no_line_without_a_body_file(self) -> None:
        with pytest.raises(ValueError, match=r"files the body from a FILE"):
            gh_command_line(a_report(), "   ")
        with pytest.raises(TypeError, match=r"never None"):
            gh_command_line(a_report(), None)  # type: ignore[arg-type]

    def test_a_skill_report_files_under_its_own_category(self) -> None:
        line = gh_command_line(
            a_report(category=FeedbackCategory.SKILL, step="narrativetrace-doctor, step 2"),
            _BODY_FILE,
        )

        assert "--label category:skill" in line
        assert "--title 'skill: narrativetrace-doctor, step 2'" in line
