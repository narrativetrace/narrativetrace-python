# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What the verb can learn about a project without being told: which NarrativeTrace it resolved, and
which structural trace is safe to attach.
"""

from __future__ import annotations

import pytest
from reports import STRUCTURAL_TRACE, doctor_snapshot

from narrativetrace_tooling.doctor.types import DoctorSnapshot, PackageInfo
from narrativetrace_tooling.feedback.gatherer import (
    INSTALL_UNKNOWN,
    TraceChoice,
    attachments_for,
    choose_trace,
    install_coordinate,
)

_RENDERED_TRACE = """scenario: Order is placed

- OrderService.place_order(customer_id: "C-1234") → "ORD-9001" — 1ms
"""
"""A rendered narrative somebody saved under a ``.nt`` name: not the grammar at all."""

_SECRET_IN_THE_HEADER = """scenario: Order placed with password: hunter2

- OrderService.place_order(customer_id)
"""
"""A trace that IS the grammar and still may not be filed — somebody put a credential in a test
name. The two halves of ``_is_attachable`` are different questions, and this is the one only the
value-free rules can answer."""


def _snapshot(**overrides: object) -> DoctorSnapshot:
    base = doctor_snapshot()
    return DoctorSnapshot(
        cwd=base.cwd,
        python_version=base.python_version,
        env=base.env,
        root_pyproject=base.root_pyproject,
        narrativetrace_config=base.narrativetrace_config,
        source_files=base.source_files,
        **overrides,  # type: ignore[arg-type]
    )


def _installed(**versions: str) -> dict[str, PackageInfo]:
    return {name: PackageInfo(name=name, version=version) for name, version in versions.items()}


class TestTheInstallCoordinate:
    def test_names_every_narrativetrace_distribution_this_project_resolved(self) -> None:
        snapshot = _snapshot(
            installed_packages=_installed(
                **{"narrativetrace": "0.2.0", "narrativetrace-pytest": "0.2.0", "pytest": "8.3.4"}
            )
        )

        assert install_coordinate(snapshot) == "narrativetrace==0.2.0, narrativetrace-pytest==0.2.0"

    def test_sorted_so_two_runs_of_the_verb_report_the_same_coordinate(self) -> None:
        snapshot = _snapshot(
            installed_packages=_installed(
                **{"narrativetrace-pytest": "0.2.0", "narrativetrace": "0.2.0"}
            )
        )

        assert install_coordinate(snapshot).startswith("narrativetrace==")

    def test_a_third_party_distribution_is_not_ours_however_it_is_spelled(self) -> None:
        """``startswith`` on a distribution name is the near-miss trap: ``narrativetracer`` is
        somebody else's package and must not appear in our install coordinate."""
        snapshot = _snapshot(
            installed_packages=_installed(**{"narrativetracer": "9.9.9", "pytest": "8.3.4"})
        )

        assert install_coordinate(snapshot) == INSTALL_UNKNOWN

    def test_a_project_that_resolved_none_of_ours_says_so(self) -> None:
        """The empty-project path the install prompt starts from. A blank field would read, to
        triage, as a verb that failed to look."""
        assert install_coordinate(_snapshot()) == INSTALL_UNKNOWN


class TestChoosingAStructuralTrace:
    def test_attaches_the_first_clean_structural_trace_in_path_order(self) -> None:
        snapshot = _snapshot(
            output_files={
                "structural/B/second.nt": STRUCTURAL_TRACE,
                "structural/A/first.nt": STRUCTURAL_TRACE,
                "A/first.md": "# a rendered narrative",
            }
        )

        choice = choose_trace(snapshot, "")

        assert choice.content == STRUCTURAL_TRACE
        assert choice.reason == ""

    def test_reads_an_approved_trace_as_well_as_the_output_directory(self) -> None:
        snapshot = _snapshot(approved_dir_files={"A/first.approved.nt": STRUCTURAL_TRACE})

        assert choose_trace(snapshot, "").content == STRUCTURAL_TRACE

    def test_skips_a_candidate_a_value_free_rule_refuses(self) -> None:
        snapshot = _snapshot(
            output_files={
                "structural/A/first.nt": _SECRET_IN_THE_HEADER,
                "structural/B/second.nt": STRUCTURAL_TRACE,
            }
        )

        assert choose_trace(snapshot, "").content == STRUCTURAL_TRACE

    def test_skips_a_candidate_that_is_not_the_grammar(self) -> None:
        snapshot = _snapshot(
            output_files={
                "structural/A/first.nt": _RENDERED_TRACE,
                "structural/B/second.nt": STRUCTURAL_TRACE,
            }
        )

        assert choose_trace(snapshot, "").content == STRUCTURAL_TRACE

    def test_says_why_rather_than_attaching_nothing_silently(self) -> None:
        """A report that quietly lost its attachment is a report whose author thinks they filed
        more than they did."""
        snapshot = _snapshot(output_files={"structural/A/first.nt": _SECRET_IN_THE_HEADER})

        choice = choose_trace(snapshot, "")

        assert choice.content == ""
        assert choice.reason.startswith("no attachable structural trace: structural/A/first.nt")
        assert "vf.named-secret" in choice.reason

    def test_a_file_that_is_not_a_structural_trace_at_all_says_that_instead(self) -> None:
        snapshot = _snapshot(output_files={"structural/A/first.nt": "INFO starting up\n"})

        assert "is not a structural trace" in choose_trace(snapshot, "").reason

    def test_a_project_with_no_trace_at_all_says_so(self) -> None:
        assert choose_trace(_snapshot(), "").reason == (
            "no structural trace was found under this project's output"
        )

    def test_a_named_path_is_honoured_by_its_suffix(self) -> None:
        snapshot = _snapshot(
            output_files={
                "structural/A/first.nt": STRUCTURAL_TRACE,
                "structural/B/second.nt": STRUCTURAL_TRACE.replace("Order", "Invoice"),
            }
        )

        choice = choose_trace(snapshot, "B/second.nt")

        assert "Invoice" in choice.content

    def test_a_named_path_that_is_not_attachable_says_why_about_that_file(self) -> None:
        snapshot = _snapshot(
            output_files={
                "structural/A/first.nt": _SECRET_IN_THE_HEADER,
                "structural/B/second.nt": STRUCTURAL_TRACE,
            }
        )

        choice = choose_trace(snapshot, "A/first.nt")

        assert choice.content == ""
        assert choice.reason == "A/first.nt breaks vf.named-secret"

    def test_a_named_path_nobody_has_says_it_was_not_found(self) -> None:
        choice = choose_trace(_snapshot(output_files={"a/b.nt": STRUCTURAL_TRACE}), "nope.nt")

        assert choice.reason == "nope.nt was not found under this project's output"

    def test_a_choice_is_content_or_a_reason_never_both_and_never_neither(self) -> None:
        with pytest.raises(ValueError, match=r"never both and never neither"):
            TraceChoice("", "")
        with pytest.raises(ValueError, match=r"never both and never neither"):
            TraceChoice(STRUCTURAL_TRACE, "and a reason")

    def test_an_absent_half_of_a_choice_is_the_empty_string_never_none(self) -> None:
        """``None`` would pass the exclusivity test by being falsy and then reach the report as an
        attachment nobody can read."""
        with pytest.raises(TypeError, match=r"never None"):
            TraceChoice(None, "a reason")  # type: ignore[arg-type]
        with pytest.raises(TypeError, match=r"never None"):
            TraceChoice(STRUCTURAL_TRACE, None)  # type: ignore[arg-type]


class TestTheAttachmentSet:
    def test_carries_the_doctors_json_and_the_chosen_trace(self) -> None:
        snapshot = _snapshot(output_files={"structural/A/first.nt": STRUCTURAL_TRACE})

        attachments = attachments_for(snapshot, '{"findings": []}', "")

        assert attachments.doctor_report == '{"findings": []}'
        assert attachments.structural_trace == STRUCTURAL_TRACE

    def test_a_project_whose_doctor_could_not_run_says_why(self) -> None:
        attachments = attachments_for(_snapshot(), "", "no readable pyproject.toml")

        assert not attachments.has_doctor_report
        assert attachments.doctor_unavailable == "no readable pyproject.toml"

    def test_a_blank_doctor_report_with_no_reason_is_a_callers_bug(self) -> None:
        """Exclusive and exhaustive is the attachment set's own invariant; this is the path that
        would otherwise produce "no report and no reason", which triage reads as a reporter who
        did not bother."""
        with pytest.raises(ValueError, match=r"never both and never neither"):
            attachments_for(_snapshot(), "", "")
