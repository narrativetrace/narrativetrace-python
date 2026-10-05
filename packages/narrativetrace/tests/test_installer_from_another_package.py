# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The installer as an ENTRY POINT sees it: another distribution, the carrier a real install
resolves, a real directory.

This suite lives in the ``narrativetrace`` distribution on purpose. That is the distribution whose
console script will drive the installer, and nothing here reaches past
:mod:`narrativetrace_tooling.init`'s own surface — so anything load-bearing that is accidentally
private fails here rather than passing in a same-package test.

These are also the only end-to-end cases: resolve the carrier this project really resolves, install
into an empty project, install again, uninstall, and check the tree at each step.

Named after the Java port's ``InstallerFromAnotherPackageTest`` so the two lists diff.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from narrativetrace_tooling.init import (
    Carrier,
    ExecutionReport,
    InitOptions,
    Scope,
    execute_plan,
    plan_init,
    plan_uninstall,
    project_family_version,
    read_project_state,
    render_plan,
    render_report,
    resolve_carrier,
    version_warning,
)


@pytest.fixture(scope="session")
def carrier() -> Carrier:
    """Whatever an install in this repository really resolves — never a fixture carrier."""
    return resolve_carrier()


def install(project: Path, carrier: Carrier, options: InitOptions) -> ExecutionReport:
    plan = plan_init(read_project_state(project), carrier, options)
    return execute_plan(plan, project)


def files_under(project: Path) -> list[str]:
    return sorted(str(file.relative_to(project)) for file in project.rglob("*") if file.is_file())


class TestInstallingIntoAnEmptyProject:
    def test_installs_the_carriers_skills_and_the_managed_section(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        report = install(tmp_path, carrier, InitOptions())

        assert report.exit_code == 0
        assert report.carrier == carrier.coordinate
        for skill in carrier.skills:
            page = tmp_path / ".agents/skills" / skill.name / "SKILL.md"
            assert page.is_file()
            text = page.read_text(encoding="utf-8")
            assert f"installed by narrativetrace init from {carrier.coordinate}" in text
            assert skill.name in text
        section = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert section.startswith("<!-- narrativetrace:created -->")
        assert f"<!-- narrativetrace:start {carrier.coordinate} -->" in section
        assert "<!-- narrativetrace:end -->" in section

    def test_installs_the_vendor_flavour_only_where_it_is_wanted(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        (tmp_path / ".claude").mkdir()

        install(tmp_path, carrier, InitOptions())

        installed = files_under(tmp_path)
        assert any(name.startswith(".claude/skills/") for name in installed)
        assert any(name.startswith(".agents/skills/") for name in installed)

    def test_a_second_install_of_the_same_carrier_has_nothing_to_do(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        install(tmp_path, carrier, InitOptions())

        second = plan_init(read_project_state(tmp_path), carrier, InitOptions())

        assert second.is_empty is True
        assert "nothing to do" in render_plan(second, as_json=False)

    def test_a_dry_run_shows_the_diff_and_writes_nothing(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        options = InitOptions(dry_run=True)

        plan = plan_init(read_project_state(tmp_path), carrier, options)
        shown = render_plan(plan, as_json=False)

        assert "--- /dev/null" in shown
        assert "+++ b/AGENTS.md" in shown
        assert "+## NarrativeTrace" in shown
        assert files_under(tmp_path) == []
        assert plan.exit_code == 0

    def test_installs_only_the_half_it_is_asked_for(self, carrier: Carrier, tmp_path: Path) -> None:
        install(tmp_path, carrier, InitOptions(scope=Scope.SKILLS))

        installed = files_under(tmp_path)
        assert installed != []
        assert "AGENTS.md" not in installed

    def test_reads_back_what_it_wrote_as_a_project_state(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        install(tmp_path, carrier, InitOptions())

        state = read_project_state(tmp_path)

        assert state.agents_md is not None
        assert state.installed_skills != ()
        assert {skill.coordinate for skill in state.installed_skills} == {carrier.coordinate}


class TestUninstalling:
    def test_uninstalling_takes_back_everything_the_install_wrote(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        install(tmp_path, carrier, InitOptions())

        report = execute_plan(plan_uninstall(read_project_state(tmp_path), InitOptions()), tmp_path)

        assert report.exit_code == 0
        assert files_under(tmp_path) == []

    def test_uninstalling_names_the_carrier_it_removed(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        install(tmp_path, carrier, InitOptions())

        plan = plan_uninstall(read_project_state(tmp_path), InitOptions())

        assert plan.carrier == carrier.coordinate


class TestWhatAnExistingProjectGetsBack:
    def test_refuses_an_existing_context_file_and_says_what_to_pass(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        (tmp_path / "AGENTS.md").write_text("# My own notes\n", encoding="utf-8")

        report = install(tmp_path, carrier, InitOptions())

        assert report.exit_code == 1
        assert "--write-existing" in render_report(report, as_json=False)
        assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "# My own notes\n"
        assert any(name.startswith(".agents/skills/") for name in files_under(tmp_path))

    def test_the_json_envelope_names_the_carrier_every_action_and_the_exit_code(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        report = install(tmp_path, carrier, InitOptions())

        payload = json.loads(render_report(report, as_json=True))

        assert payload["carrier"] == carrier.coordinate
        assert {"kind": "create", "path": "AGENTS.md", "status": "applied"} in payload["actions"]
        assert payload["exit_code"] == 0


class TestTheVersionGuardInItsRealSetting:
    def test_says_nothing_when_the_carrier_matches_the_release_this_project_runs(
        self, carrier: Carrier
    ) -> None:
        assert version_warning(carrier, project_family_version()) is None
