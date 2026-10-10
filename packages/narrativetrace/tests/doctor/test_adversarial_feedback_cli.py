# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial pass (milestone 2) over the verb: behaviour asserted by no other test.

CURATED, the same way ``tests/feedback/test_adversarial_feedback.py`` is. The generated candidates
for this file were almost all duplicates of ``test_cli_feedback_verb.py``, and the rest asserted
things that cannot fail — including one literal ``assert "~" in body or body``, whose second
disjunct is a non-empty string.

What survived is the cross-CHANNEL and cross-FIELD behaviour: the body file is the same whichever
channel wrote it, a refusal names every field that broke rather than the first, and the home-path
rewrite reaches the two platform spellings the existing case does not.

``Run`` is imported from ``test_cli_feedback_verb`` rather than copied: a second copy of the
launcher's dependency wiring is a second place for the seam to drift. The two path constants come
from the verb itself, not through that module — a test module is not an export surface, and mypy
says so.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_cli_feedback_verb import Run

from narrativetrace.doctor.feedback_cli import BODY_FILE, DRAFT_FILE


@pytest.fixture
def project(tmp_path: Path) -> Path:
    directory = tmp_path / "project"
    directory.mkdir()
    return directory


def _with_narrative(run: Run, channel: str, did: str) -> int:
    return run.cli(
        "feedback",
        channel,
        "--category",
        "doctor",
        "--step",
        "trap.redaction-proof",
        "--did",
        did,
        "--happened",
        "it failed",
        "--expected",
        "it to pass",
    )


class TestTheBodyFileIsTheSameWhicheverChannelWroteIt:
    def test_draft_and_url_write_the_same_body(self, project: Path) -> None:
        """The URL tells the reporter to paste this file, and `draft` is what they were shown. If
        the two channels could write different bytes, the report filed would not be the report
        approved — and nothing would say so, because each channel is correct on its own."""
        run = Run(project)

        run.feedback("draft")
        from_draft = run.written(BODY_FILE)
        run.feedback("url")

        assert run.written(BODY_FILE) == from_draft

    def test_and_so_does_gh(self, project: Path) -> None:
        run = Run(project, gh_signed_in=True)

        run.feedback("draft")
        from_draft = run.written(BODY_FILE)
        run.feedback("gh")

        assert run.written(BODY_FILE) == from_draft

    def test_a_channel_that_prints_a_link_still_leaves_the_draft_behind(
        self, project: Path
    ) -> None:
        """Both files, on every cleared channel: the reporter who chose `url` may still want to
        read what they are about to file."""
        run = Run(project)

        run.feedback("url")

        assert (project / DRAFT_FILE).is_file()
        assert run.written(BODY_FILE) in run.written(DRAFT_FILE)


class TestARefusalNamesEveryFieldThatBroke:
    def test_two_different_fields_are_both_named_in_field_order(self, project: Path) -> None:
        """Every existing refusal case breaks ONE field. A reporter who has to fix two and is told
        about one fixes it, re-runs, and is refused again — which is the shape that teaches people
        to route around a gate."""
        run = Run(project)

        exit_code = run.cli(
            "feedback",
            "draft",
            "--category",
            "doctor",
            "--step",
            "trap.redaction-proof",
            "--did",
            "ada@example.com hit it",
            "--happened",
            'it rendered as OrderService.place_order(id: "C-1")',
            "--expected",
            "it to pass",
        )

        assert exit_code == 2
        assert "did: vf.email" in run.stderr
        assert "happened: vf.rendered-call" in run.stderr
        assert run.stderr.index("did:") < run.stderr.index("happened:"), (
            "field order, so the same report always refuses in the same words"
        )
        assert "2 rule(s) refused it" in run.stderr


class TestTheHomePathRewriteThroughTheVerb:
    @pytest.mark.parametrize(
        ("typed", "expected"),
        [
            ("ran it from /home/alice/project", "ran it from ~/project"),
            ("ran it from C:\\Users\\Alice\\project", "ran it from ~\\project"),
        ],
        ids=["linux", "windows"],
    )
    def test_each_platform_spelling_is_rewritten_end_to_end(
        self, project: Path, typed: str, expected: str
    ) -> None:
        """The existing case covers the macOS spelling. These two reach the rewriter through the
        whole verb, which is where a report from a Linux CI box or a Windows laptop actually comes
        from — and where `vf.home-path` would otherwise refuse it."""
        run = Run(project)

        assert _with_narrative(run, "draft", typed) == 0
        assert expected in run.written(BODY_FILE)
        assert "alice" not in run.written(BODY_FILE).lower()

    def test_a_relative_path_reaches_the_report_unchanged(self, project: Path) -> None:
        """The other direction, through the verb: an eager rewrite would turn an ordinary path
        into ``~`` and make the report wrong instead of safe."""
        run = Run(project)

        assert _with_narrative(run, "draft", "the trace was at build/narrativetrace/x.nt") == 0
        assert "build/narrativetrace/x.nt" in run.written(BODY_FILE)
