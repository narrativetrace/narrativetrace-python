# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The properties that have to hold for a tree the installer did NOT create: the one a registry
leaves behind.

Every example builds a real temp project shaped like an ``npx skills add`` install — the rendered
pages of one flavour, a symbolic link at the other flavour's path, and a lock file of the registry's
own — and then runs the installer over it.

Three dimensions, because each one has broken something in a port at some point: which flavour's
path is the link, whether the link is the DIRECTORY or the page inside it, and which line ending the
checked-out pages carry. (Java's own milestone-2 note calls these "four dimensions" while
enumerating these three; the generators here mirror Java's three ``@ForAll`` parameters exactly, so
the two ports cover the same eight trees.)

Named after the Java port's ``RegistryTreePropertyTest`` so the two lists diff; its jqwik generators
become Hypothesis strategies over the same choices.
"""

from __future__ import annotations

from pathlib import Path

import carriers
import projects
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from narrativetrace_tooling.init import provenance
from narrativetrace_tooling.init.carrier import Carrier
from narrativetrace_tooling.init.catalogue import SkillFlavour
from narrativetrace_tooling.init.init_planner import plan_init
from narrativetrace_tooling.init.options import InitOptions
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.plan_executor import execute_plan
from narrativetrace_tooling.init.plan_renderer import render_plan_text
from narrativetrace_tooling.init.project_state import PAGE
from narrativetrace_tooling.init.project_state_reader import read_project_state
from narrativetrace_tooling.init.report import ExecutionReport
from narrativetrace_tooling.init.uninstall_planner import plan_uninstall

LOCK_FILE = '{"skills": []}\n'
"""What ``npx skills add`` writes at the project root; nothing of ours may touch it."""

LOCK_FILE_NAME = "skills-lock.json"

LINE_ENDINGS = st.sampled_from(["\n", "\r\n"])


@pytest.fixture(scope="session")
def registry_carrier(tmp_path_factory: pytest.TempPathFactory) -> Carrier:
    """One hand-built carrier for the whole session: the properties build dozens of projects, and
    none of them cares which skills the carrier lists — only that the two flavours' pages differ.

    Session-scoped on purpose — a function-scoped fixture would be built once and reused across
    every generated example, which Hypothesis rightly refuses.
    """
    return carriers.fake(tmp_path_factory.mktemp("registry-carrier"), "doctor", "clarity")


# --- the tree a registry leaves -------------------------------------------------------------------


def registry_tree(
    project: Path, carrier: Carrier, *, link_the_vendor_path: bool, link_the_page: bool, eol: str
) -> None:
    """One flavour's pages for real, the other flavour's path a link to them, and the lock file.

    The real pages are this carrier's own rendering — that is what a registry installs — carrying
    the line ending of whoever checked them out.
    """
    real = SkillFlavour.AGENTS if link_the_vendor_path else SkillFlavour.CLAUDE
    linked = SkillFlavour.CLAUDE if link_the_vendor_path else SkillFlavour.AGENTS
    (project / linked.install_root).mkdir(parents=True, exist_ok=True)
    for skill in carrier.skills:
        page = project / real.install_root / skill.name / PAGE
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_bytes(carrier.body(skill, real).replace("\n", eol).encode("utf-8"))
        _link(project / linked.install_root / skill.name, page, link_the_page=link_the_page)
    (project / LOCK_FILE_NAME).write_bytes(LOCK_FILE.encode("utf-8"))


def _link(at: Path, page: Path, *, link_the_page: bool) -> None:
    """The link a registry makes: the directory itself, or a real directory with a linked page."""
    if not link_the_page:
        at.symlink_to(page.parent)
        return
    at.mkdir(parents=True)
    (at / PAGE).symlink_to(page)


def plan(project: Path, carrier: Carrier) -> InitPlan:
    return plan_init(read_project_state(project), carrier, InitOptions())


def install(project: Path, carrier: Carrier) -> ExecutionReport:
    return execute_plan(plan(project, carrier), project)


def assert_every_page_is_its_own_flavour(project: Path, carrier: Carrier) -> None:
    """The assertion a write through a link would fail: every flavour's own path holds its OWN
    flavour's stamped page, as a real file."""
    for skill in carrier.skills:
        for flavour in SkillFlavour:
            page = project / flavour.install_root / skill.name / PAGE
            assert not page.is_symlink(), f"{page} is a real file"
            assert page.read_bytes().decode("utf-8") == provenance.stamp(
                carrier.body(skill, flavour), carrier.coordinate
            ), f"{page} holds the {flavour.value} flavour"


# --- the properties -------------------------------------------------------------------------------


@settings(max_examples=40, deadline=None)
@given(link_the_vendor_path=st.booleans(), link_the_page=st.booleans(), eol=LINE_ENDINGS)
def test_a_registry_tree_is_adopted_without_writing_through_its_links(
    registry_carrier: Carrier, link_the_vendor_path: bool, link_the_page: bool, eol: str
) -> None:
    """The whole of D5's promise: the pages are adopted, the link is replaced by a real path, and
    NOTHING is written through the link — each flavour's path ends up holding its own flavour's
    page, which is exactly what a write through the link would have destroyed.

    The proof that adoption happened is the PLAN, not the exit code: a run that refused everything
    also exits 0 on a dry run, and a run that overwrote everything exits 0 for real.
    """
    with projects.in_a_temporary_one("narrativetrace-registry") as project:
        registry_tree(
            project,
            registry_carrier,
            link_the_vendor_path=link_the_vendor_path,
            link_the_page=link_the_page,
            eol=eol,
        )

        planned = plan(project, registry_carrier)
        report = execute_plan(planned, project)

        kinds = {action.kind for action in planned.actions}
        assert planned.refusals == (), render_plan_text(planned)
        assert "adopt" in kinds, render_plan_text(planned)
        assert "replace-link" in kinds, render_plan_text(planned)
        assert report.exit_code == 0, "a registry tree needs no flag"
        assert_every_page_is_its_own_flavour(project, registry_carrier)
        assert (project / LOCK_FILE_NAME).read_bytes().decode("utf-8") == LOCK_FILE


@settings(max_examples=40, deadline=None)
@given(link_the_vendor_path=st.booleans(), link_the_page=st.booleans(), eol=LINE_ENDINGS)
def test_planning_again_after_adopting_a_registry_tree_finds_nothing_to_do(
    registry_carrier: Carrier, link_the_vendor_path: bool, link_the_page: bool, eol: str
) -> None:
    """Idempotence, over a tree we did not write."""
    with projects.in_a_temporary_one("narrativetrace-registry") as project:
        registry_tree(
            project,
            registry_carrier,
            link_the_vendor_path=link_the_vendor_path,
            link_the_page=link_the_page,
            eol=eol,
        )
        install(project, registry_carrier)
        adopted = projects.snapshot_of(project)

        second = plan(project, registry_carrier)
        install(project, registry_carrier)

        assert second.is_empty, render_plan_text(second)
        assert projects.snapshot_of(project) == adopted


@settings(max_examples=40, deadline=None)
@given(link_the_vendor_path=st.booleans(), link_the_page=st.booleans(), eol=LINE_ENDINGS)
def test_uninstalling_after_adopting_leaves_the_registrys_own_files_and_no_link(
    registry_carrier: Carrier, link_the_vendor_path: bool, link_the_page: bool, eol: str
) -> None:
    """Uninstalling gives back the registry's own tree minus the pages, which adoption made ours.
    The lock file is the registry's and stays; a page identical to this release's was never
    anybody else's work to keep."""
    with projects.in_a_temporary_one("narrativetrace-registry") as project:
        registry_tree(
            project,
            registry_carrier,
            link_the_vendor_path=link_the_vendor_path,
            link_the_page=link_the_page,
            eol=eol,
        )
        install(project, registry_carrier)

        report = execute_plan(plan_uninstall(read_project_state(project), InitOptions()), project)

        assert report.exit_code == 0
        assert list(projects.snapshot_of(project)) == [LOCK_FILE_NAME]
        assert projects.links_under(project) == []


def test_the_generator_really_builds_the_tree_the_properties_are_about(
    registry_carrier: Carrier, tmp_path: Path
) -> None:
    """A property over a tree that never has a link in it proves nothing. One example-based check
    per axis that the fixture builder produces what it claims: a linked directory, a linked page,
    the vendor path linked, the open-standard path linked, and a CRLF checkout."""
    built: dict[str, list[str]] = {}
    for vendor in (True, False):
        for page in (True, False):
            project = tmp_path / f"tree-{vendor}-{page}"
            project.mkdir()
            registry_tree(
                project,
                registry_carrier,
                link_the_vendor_path=vendor,
                link_the_page=page,
                eol="\r\n",
            )
            built[f"{vendor}-{page}"] = projects.links_under(project)

    assert built["True-False"] == [".claude/skills/clarity", ".claude/skills/doctor"]
    assert built["True-True"] == [
        ".claude/skills/clarity/SKILL.md",
        ".claude/skills/doctor/SKILL.md",
    ]
    assert built["False-False"] == [".agents/skills/clarity", ".agents/skills/doctor"]
    assert "\r\n" in (
        tmp_path / "tree-True-False/.agents/skills/doctor/SKILL.md"
    ).read_bytes().decode("utf-8")


def test_the_two_flavours_pages_differ_or_the_properties_prove_nothing(
    registry_carrier: Carrier,
) -> None:
    """Every "each path holds its own flavour" assertion is vacuous if the two renderings are
    equal — and a write through a link would then be undetectable by construction."""
    for skill in registry_carrier.skills:
        assert registry_carrier.body(skill, SkillFlavour.AGENTS) != registry_carrier.body(
            skill, SkillFlavour.CLAUDE
        )


def test_a_real_directory_is_only_adoptable_against_its_own_flavour(
    registry_carrier: Carrier,
) -> None:
    """The planner compares a page reached through a LINK against either flavour (the link a
    registry leaves points at the open-standard page) and a page in a REAL directory against its
    own only.

    This pins the second half. A registry that copied instead of linking would leave the
    open-standard page at the vendor path for real, and adopting it there would stamp the wrong
    flavour as though it were right — so it is a refusal.
    """
    with projects.in_a_temporary_one("narrativetrace-copied") as project:
        for skill in registry_carrier.skills:
            for flavour in SkillFlavour:
                page = project / flavour.install_root / skill.name / PAGE
                page.parent.mkdir(parents=True)
                page.write_bytes(registry_carrier.body(skill, SkillFlavour.AGENTS).encode("utf-8"))

        planned = plan(project, registry_carrier)

        kinds = {action.path.as_posix(): action.kind for action in planned.actions}
        assert kinds[".agents/skills/doctor/SKILL.md"] == "adopt"
        assert kinds[".claude/skills/doctor"] == "refuse"
        assert ".claude/skills/doctor/SKILL.md" not in kinds
