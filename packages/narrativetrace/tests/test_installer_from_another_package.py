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

import dataclasses
import json
from pathlib import Path

import pytest

from narrativetrace_tooling.init import (
    Carrier,
    ExecutionReport,
    InitOptions,
    InstalledSkill,
    Presence,
    Scope,
    SkillFlavour,
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


def without_the_stamp(page: str) -> str:
    """The page as the carrier carries it: the installed copy minus the one provenance line and the
    blank line after it. Spelled out here rather than imported, because a consumer only ever has the
    library's public surface and the page itself."""
    lines = page.split("\n")
    kept = [line for line in lines if "installed by narrativetrace init from " not in line]
    return "\n".join(kept)


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


_GATED_SKILLS = frozenset(
    {"narrativetrace-feedback", "narrativetrace-verify", "narrativetrace-debug"}
)
"""The skills that declare no allowed tools: their steps file something public or promote a
baseline, and the harness must ask before either."""


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


class TestARegistryTreeFromOutsideTheLibrary:
    """Phase 4 milestone 2 (design D5), through the public surface only, against the carrier this
    repository really resolves — so the pages a registry would install are the real rendered pages,
    not a fixture's.

    The proof is the PLAN (what ``init --dry-run --json`` prints), never an exit code: a dry run
    exits 0 whatever it decided, and a run that overwrote everything exits 0 too.
    """

    def registry_tree(self, project: Path, carrier: Carrier) -> None:
        """What ``npx skills add`` leaves: the open-standard pages for real, and the vendor path a
        symbolic link to each of them."""
        (project / ".claude/skills").mkdir(parents=True)
        for skill in carrier.skills:
            page = project / ".agents/skills" / skill.name / "SKILL.md"
            page.parent.mkdir(parents=True)
            page.write_text(carrier.body(skill, SkillFlavour.AGENTS), encoding="utf-8")
            (project / ".claude/skills" / skill.name).symlink_to(page.parent)
        (project / "skills-lock.json").write_text('{"skills": []}\n', encoding="utf-8")

    def test_a_dry_run_plan_says_adopt_and_replace_link_and_refuses_nothing(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        self.registry_tree(tmp_path, carrier)

        plan = plan_init(
            read_project_state(tmp_path), carrier, dataclasses.replace(InitOptions(), dry_run=True)
        )
        payload = json.loads(render_plan(plan, as_json=True))

        kinds = {row["kind"] for row in payload["actions"]}
        assert "adopt" in kinds
        assert "replace-link" in kinds
        assert "refuse" not in kinds
        assert files_under(tmp_path) == [
            ".agents/skills/add-narrative-tracing/SKILL.md",
            ".agents/skills/add-narrativetrace-clarity/SKILL.md",
            ".agents/skills/narrativetrace-debug/SKILL.md",
            ".agents/skills/narrativetrace-doctor/SKILL.md",
            ".agents/skills/narrativetrace-feedback/SKILL.md",
            ".agents/skills/narrativetrace-verify/SKILL.md",
            "skills-lock.json",
        ], "a dry run writes nothing"

    def test_a_real_run_adopts_the_pages_and_leaves_each_flavour_its_own(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        self.registry_tree(tmp_path, carrier)

        report = install(tmp_path, carrier, InitOptions())

        assert report.exit_code == 0
        for skill in carrier.skills:
            for flavour in SkillFlavour:
                page = tmp_path / flavour.install_root / skill.name / "SKILL.md"
                written = page.read_text(encoding="utf-8")
                assert not page.is_symlink()
                assert carrier.coordinate in written
                assert without_the_stamp(written) == carrier.body(skill, flavour), (
                    f"{page} is this carrier's own {flavour.value} page plus one line"
                )

    def test_the_vendor_page_is_the_vendor_flavour_and_not_what_the_link_reached(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        """The one assertion a write through the link would fail, keyed on the vendor-only
        frontmatter: ``when_to_use`` on every skill, and ``allowed-tools`` on every skill that
        declares tools. The reporting skill declares none, by design -- so its vendor page must
        carry NO ``allowed-tools`` line either, the link or no link."""
        self.registry_tree(tmp_path, carrier)

        install(tmp_path, carrier, InitOptions())

        for skill in carrier.skills:
            vendor = (tmp_path / ".claude/skills" / skill.name / "SKILL.md").read_text(
                encoding="utf-8"
            )
            open_standard = (tmp_path / ".agents/skills" / skill.name / "SKILL.md").read_text(
                encoding="utf-8"
            )
            assert "when_to_use:" in vendor
            assert "when_to_use:" not in open_standard
            assert ("allowed-tools:" in vendor) == (skill.name not in _GATED_SKILLS)
            assert "allowed-tools:" not in open_standard

    def test_the_registrys_own_lock_file_is_never_touched(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        self.registry_tree(tmp_path, carrier)

        install(tmp_path, carrier, InitOptions())
        execute_plan(plan_uninstall(read_project_state(tmp_path), InitOptions()), tmp_path)

        assert (tmp_path / "skills-lock.json").read_text(encoding="utf-8") == '{"skills": []}\n'
        assert files_under(tmp_path) == ["skills-lock.json"]

    def test_a_page_a_person_edited_is_still_refused_without_the_flag(
        self, carrier: Carrier, tmp_path: Path
    ) -> None:
        """Adoption is for a page identical to ours. One line of somebody's own editing and the
        refusal is back — which is the whole reason adoption is safe."""
        self.registry_tree(tmp_path, carrier)
        edited = tmp_path / ".agents/skills" / carrier.skills[0].name / "SKILL.md"
        edited.write_text(
            carrier.body(carrier.skills[0], SkillFlavour.AGENTS) + "my own note\n", encoding="utf-8"
        )

        plan = plan_init(read_project_state(tmp_path), carrier, InitOptions())

        refused_paths = {refusal.path.as_posix() for refusal in plan.refusals}
        assert f".agents/skills/{carrier.skills[0].name}" in refused_paths

    def test_the_linked_presences_and_their_guards_are_public(self) -> None:
        """``Presence`` and ``InstalledSkill`` are part of the library's surface — an entry point
        reads them to describe a project — so the two new members and the link guard are asserted
        from outside the package that defines them."""
        linked = InstalledSkill(
            SkillFlavour.CLAUDE,
            "narrativetrace-doctor",
            Presence.LINKED_DIRECTORY,
            body="page\n",
            link="../../.agents/skills/narrativetrace-doctor",
        )

        assert linked.linked_at == Path(".claude/skills/narrativetrace-doctor")
        assert Presence.LINKED_PAGE.value == "linked-page"
        with pytest.raises(ValueError, match=r"names what the link points at"):
            InstalledSkill(SkillFlavour.AGENTS, "d", Presence.FOREIGN, link="somewhere")
