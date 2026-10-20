# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Three wording gaps a directory listing exposes, pinned word for word because a reader acts on
this text: a plugin install is invisible to the doctor's project check; verify opens values on a
data symptom too, not only on a shape mismatch; and one trace shows one path, so a report names
the branches it did not exercise."""

from __future__ import annotations

from narrativetrace_skills.catalogue.narrativetrace_doctor import NARRATIVETRACE_DOCTOR
from narrativetrace_skills.catalogue.narrativetrace_explain import NARRATIVETRACE_EXPLAIN
from narrativetrace_skills.catalogue.narrativetrace_verify import NARRATIVETRACE_VERIFY
from narrativetrace_skills.catalogue_index import SKILLS
from narrativetrace_skills.lints import CATALOGUE_CHAR_BUDGET, catalogue_description_chars
from narrativetrace_skills.skill import SkillStep


def _step(steps: tuple[SkillStep, ...], title: str) -> SkillStep:
    return next(step for step in steps if step.title == title)


class TestDoctorSaysWhichInstallItCanSee:
    def test_the_description_says_the_skills_check_reads_this_project(self) -> None:
        assert (
            "whether the NarrativeTrace agent skills are installed in this project and current, "
            "unrecognized narrativetrace.toml keys"
        ) in NARRATIVETRACE_DOCTOR.description

    def test_the_explanation_of_a_plugin_install_lives_in_the_triggers_not_the_description(
        self,
    ) -> None:
        assert "personal plugin" not in NARRATIVETRACE_DOCTOR.description
        assert NARRATIVETRACE_DOCTOR.when_to_use == (
            "A project already has NarrativeTrace installed and something about it is not "
            "working, or an agent wants a pre-flight check before wiring it into new code. Also "
            "when a user installed these skills as a personal plugin in their agent rather than "
            "in this project: a plugin install is invisible to this check by design, and only a "
            "project install reaches teammates and other agents."
        )

    def test_the_catalogue_stays_inside_its_description_budget(self) -> None:
        assert catalogue_description_chars(SKILLS) <= CATALOGUE_CHAR_BUDGET


class TestVerifyOpensValuesOnADataSymptomToo:
    _OPEN = "Open values on the span that looks wrong, and only there"
    _FIX = "Fix, re-run, read again"

    def test_step_five_opens_the_one_span_a_symptom_points_at(self) -> None:
        assert _step(NARRATIVETRACE_VERIFY.steps, self._OPEN).condition == (
            "when the structural read named a span that does not match the intent, or the shape "
            "matches but a symptom points at data — an assertion failed on a value, the output "
            "is wrong — then open the one span the symptom points at; otherwise go on to the pin"
        )

    def test_step_six_also_runs_when_the_value_read_in_step_five_was_wrong(self) -> None:
        assert _step(NARRATIVETRACE_VERIFY.steps, self._FIX).condition == (
            "only when the structural read named a span that does not match the intent, or the "
            "value read in step 5 was wrong; otherwise go on to the pin"
        )

    def test_step_six_is_step_six(self) -> None:
        titles = [step.title for step in NARRATIVETRACE_VERIFY.steps]
        assert titles.index(self._OPEN) == 4
        assert titles.index(self._FIX) == 5


class TestOneTraceOnePath:
    def test_the_verify_report_binds_claims_to_the_path_the_run_took_and_names_the_untaken(
        self,
    ) -> None:
        report = _step(NARRATIVETRACE_VERIFY.steps, "Report what the trace showed")
        assert report.done == (
            "two sentences on what the trace showed on the path this run took, every claim "
            "citing the span id it rests on — a claim without an id is not a claim, and only ids "
            "in the .nt that was read count — with the .nt attached or quoted; the report names "
            "the branches and inputs this run did not exercise, because one trace shows one "
            "path, not every execution; 'tests pass' alone is not the report"
        )

    def test_the_explain_report_names_the_branches_the_run_did_not_take(self) -> None:
        last = NARRATIVETRACE_EXPLAIN.steps[-1]
        assert last.done is not None
        assert last.done.endswith(
            "the last part names what was NOT observed: the code no span covers, because only "
            "wrapped or intercepted code has one, and the branches this run did not take"
        )
