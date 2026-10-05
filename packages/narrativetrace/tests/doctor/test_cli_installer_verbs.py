# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace init`` and ``narrativetrace uninstall`` through the launcher, driven with
injected dependencies so no case spawns a process.

Named after the Java port's ``CliTest`` init/uninstall sections so the two case lists diff. The
project is a real temporary directory — the installer's whole job is files, and a fake filesystem
would prove only that the fake agrees with itself. The CARRIER is a hand-built fixture whose
coordinate a case can assert on; the real, resolved carrier is exercised end to end by
``test_installer_from_another_package.py`` and by the built-wheel suite.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from narrativetrace.doctor import cli_bin
from narrativetrace.doctor.cli_bin import CliDeps, main, run_cli
from narrativetrace_tooling.doctor.types import DoctorSnapshot
from narrativetrace_tooling.init import (
    Carrier,
    ProjectState,
    SkillFlavour,
    open_carrier,
    read_project_state,
)

CARRIER_COORDINATE = "narrativetrace-skills==1.2.3"
"""What the fixture carrier stamps with — its directory is named like an unpacked wheel."""

PROJECT_VERSION = "1.2.3"
"""The release the fixture project resolves, matched to the carrier so the guard stays silent."""

SKILL = "narrativetrace-doctor"

_CARRIER_DIRECTORY = "narrativetrace_skills-1.2.3"


def _page_path(name: str, flavour: SkillFlavour) -> str:
    return f"{flavour.value}/{name}/SKILL.md"


def _body(name: str, flavour: SkillFlavour) -> str:
    return f"---\nname: {name}\n---\n\n{flavour.value} body of {name}\n"


def build_carrier(parent: Path, *names: str) -> Carrier:
    """An unpacked carrier under ``parent``, one page per name in both flavours."""
    root = parent / _CARRIER_DIRECTORY / "skills"
    skills = []
    for name in names:
        for flavour in SkillFlavour:
            page = root / _page_path(name, flavour)
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(_body(name, flavour), encoding="utf-8")
        skills.append(
            {
                "name": name,
                "description": f"What {name} does.",
                "agents": _page_path(name, SkillFlavour.AGENTS),
                "claude": _page_path(name, SkillFlavour.CLAUDE),
            }
        )
    catalogue = root / "catalogue.json"
    catalogue.write_text(json.dumps({"runtime": "python", "skills": skills}), encoding="utf-8")
    return open_carrier(parent / _CARRIER_DIRECTORY)


class Run:
    """One launcher invocation's dependencies and everything it wrote, per stream."""

    def __init__(
        self, project: Path, carrier: Carrier | None = None, refusal: str | None = None
    ) -> None:
        """:param carrier: the carrier the reader answers with; ``None`` means this verb must not
            ask for one at all
        :param refusal: why the carrier reader refuses, for the cases about that
        """
        self.project = project
        self.out: list[str] = []
        self.err: list[str] = []
        self.asked_for: list[str | None] = []
        self._carrier = carrier
        self._refusal = refusal

    def _open_carrier(self, from_path: str | None) -> Carrier:
        self.asked_for.append(from_path)
        if self._refusal is not None:
            raise ValueError(self._refusal)
        if self._carrier is None:
            raise AssertionError("this command must not open a carrier")
        return self._carrier

    def deps(self, project_version: str | None = PROJECT_VERSION) -> CliDeps:
        return CliDeps(
            cwd=str(self.project),
            env={},
            build_snapshot=lambda cwd, env: _unreachable_snapshot(),
            open_carrier=self._open_carrier,
            project_version=lambda: project_version,
            log=self.out.append,
            error=self.err.append,
        )

    def cli(self, *argv: str, project_version: str | None = PROJECT_VERSION) -> int:
        return run_cli(list(argv), self.deps(project_version))

    @property
    def stdout(self) -> str:
        return "\n".join(self.out)

    @property
    def stderr(self) -> str:
        return "\n".join(self.err)


def _unreachable_snapshot() -> DoctorSnapshot:
    raise AssertionError("an installer verb must not build a doctor snapshot")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """The project the verbs run against — a sibling of the carrier, never its parent, so a case
    that lists the project's files never sees the fixture carrier."""
    directory = tmp_path / "project"
    directory.mkdir()
    return directory


@pytest.fixture
def carrier(tmp_path: Path) -> Carrier:
    return build_carrier(tmp_path / "carriers", SKILL, "add-narrative-tracing")


def files_under(project: Path) -> list[str]:
    return sorted(str(file.relative_to(project)) for file in project.rglob("*") if file.is_file())


def tree(project: Path) -> dict[str, str]:
    return {name: (project / name).read_text(encoding="utf-8") for name in files_under(project)}


def agents_page(project: Path) -> Path:
    return project / ".agents/skills" / SKILL / "SKILL.md"


class TestTheLauncher:
    def test_the_top_level_usage_lists_every_verb(self, project: Path) -> None:
        run = Run(project)

        assert run.cli("--help") == 0
        assert run.cli("-h") == 0
        for verb in ("doctor", "init", "uninstall"):
            assert f"  narrativetrace {verb}" in run.stdout

    def test_an_unknown_verb_exits_two_with_the_usage(self, project: Path) -> None:
        run = Run(project)

        assert run.cli("frobnicate") == 2
        assert "Unknown command: frobnicate" in run.stderr
        assert run.stdout == ""

    def test_a_flag_written_before_the_verb_is_the_unknown_command(self, project: Path) -> None:
        """Flags follow their verb, as the usage grammar shows; a leading one is not hunted past."""
        run = Run(project)

        assert run.cli("--json", "init") == 2
        assert "Unknown command: --json" in run.stderr

    def test_the_verb_is_case_sensitive(self, project: Path) -> None:
        run = Run(project)

        assert run.cli("Init") == 2
        assert "Unknown command: Init" in run.stderr


class TestInitOnAFreshProject:
    def test_writes_the_page_and_the_section(self, project: Path, carrier: Carrier) -> None:
        run = Run(project, carrier)

        code = run.cli("init")

        assert code == 0
        assert agents_page(project).is_file()
        assert (project / "AGENTS.md").is_file()
        assert "applied" in run.stdout

    def test_stamps_every_page_with_the_carriers_coordinate(
        self, project: Path, carrier: Carrier
    ) -> None:
        Run(project, carrier).cli("init")

        assert CARRIER_COORDINATE in agents_page(project).read_text(encoding="utf-8")

    def test_a_dry_run_writes_nothing_and_prints_the_diff(
        self, project: Path, carrier: Carrier
    ) -> None:
        run = Run(project, carrier)

        code = run.cli("init", "--dry-run")

        assert code == 0
        assert files_under(project) == []
        assert "+++ b/AGENTS.md" in run.stdout
        assert f"+++ b/.agents/skills/{SKILL}/SKILL.md" in run.stdout
        assert "@@" in run.stdout

    def test_a_second_init_of_the_same_carrier_applies_nothing(
        self, project: Path, carrier: Carrier
    ) -> None:
        Run(project, carrier).cli("init")
        again = Run(project, carrier)

        code = again.cli("init")

        assert code == 0
        assert "0 applied" in again.stdout

    def test_the_output_ends_in_exactly_one_newline(self, project: Path, carrier: Carrier) -> None:
        """The installer's renderers end every line and the doctor's do not; both reach one
        ``print``, so the launcher drops the one newline ``print`` puts back."""
        run = Run(project, carrier)

        run.cli("init")

        assert not run.out[0].endswith("\n")
        assert run.out[0].count("\n") > 0


class TestInitOnAProjectThatIsAlreadySomebodysWork:
    def test_refuses_an_existing_agents_md_and_names_the_flag(
        self, project: Path, carrier: Carrier
    ) -> None:
        (project / "AGENTS.md").write_text("# Mine\n", encoding="utf-8")
        run = Run(project, carrier)

        code = run.cli("init")

        assert code == 1
        assert "--write-existing" in run.stdout
        assert (project / "AGENTS.md").read_text(encoding="utf-8") == "# Mine\n"

    def test_write_existing_appends_the_section(self, project: Path, carrier: Carrier) -> None:
        (project / "AGENTS.md").write_text("# Mine\n", encoding="utf-8")
        run = Run(project, carrier)

        code = run.cli("init", "--write-existing")

        assert code == 0
        written = (project / "AGENTS.md").read_text(encoding="utf-8")
        assert written.startswith("# Mine\n")
        assert "<!-- narrativetrace:start " in written

    def test_force_overwrites_a_skill_directory_somebody_else_owns(
        self, project: Path, carrier: Carrier
    ) -> None:
        page = agents_page(project)
        page.parent.mkdir(parents=True)
        page.write_text("# theirs\n", encoding="utf-8")
        refused = Run(project, carrier)

        assert refused.cli("init") == 1
        assert page.read_text(encoding="utf-8") == "# theirs\n"
        assert "--force" in refused.stdout

        forced = Run(project, carrier)
        assert forced.cli("init", "--force") == 0
        assert "agents body" in page.read_text(encoding="utf-8")


class TestTheHalvesAndTheVendorFlavour:
    def test_only_skills_leaves_the_section_alone(self, project: Path, carrier: Carrier) -> None:
        code = Run(project, carrier).cli("init", "--only", "skills")

        assert code == 0
        assert agents_page(project).is_file()
        assert not (project / "AGENTS.md").exists()

    def test_only_agents_md_leaves_the_skills_alone(self, project: Path, carrier: Carrier) -> None:
        code = Run(project, carrier).cli("init", "--only", "agents-md")

        assert code == 0
        assert not agents_page(project).exists()
        assert (project / "AGENTS.md").is_file()

    def test_vendor_claude_writes_the_vendor_copy_where_nothing_shows_that_vendor(
        self, project: Path, carrier: Carrier
    ) -> None:
        Run(project, carrier).cli("init", "--vendor", "claude")

        assert (project / ".claude/skills" / SKILL / "SKILL.md").is_file()

    def test_vendor_none_skips_the_vendor_copy_even_where_it_is_detected(
        self, project: Path, carrier: Carrier
    ) -> None:
        (project / ".claude").mkdir()

        Run(project, carrier).cli("init", "--vendor", "none")

        assert not (project / ".claude/skills" / SKILL / "SKILL.md").exists()
        assert agents_page(project).is_file()


class TestTheJsonEnvelope:
    def test_init_prints_the_envelope_in_this_runtimes_own_casing(
        self, project: Path, carrier: Carrier
    ) -> None:
        run = Run(project, carrier)

        code = run.cli("init", "--json")

        assert code == 0
        payload = json.loads(run.out[0])
        assert payload["carrier"] == CARRIER_COORDINATE
        assert {"kind": "create", "path": "AGENTS.md", "status": "applied"} in payload["actions"]
        assert payload["exit_code"] == 0

    def test_a_dry_run_reports_planned_actions_and_exits_zero_despite_a_refusal(
        self, project: Path, carrier: Carrier
    ) -> None:
        (project / "AGENTS.md").write_text("# Mine\n", encoding="utf-8")
        run = Run(project, carrier)

        code = run.cli("init", "--dry-run", "--json")

        assert code == 0
        payload = json.loads(run.out[0])
        assert "refused" in {action["status"] for action in payload["actions"]}
        assert payload["exit_code"] == 0

    def test_uninstall_prints_the_same_envelope(self, project: Path, carrier: Carrier) -> None:
        Run(project, carrier).cli("init")
        run = Run(project)

        code = run.cli("uninstall", "--json")

        assert code == 0
        payload = json.loads(run.out[0])
        assert payload["carrier"] == CARRIER_COORDINATE
        assert payload["exit_code"] == 0


class TestTheVerbsOwnUsage:
    def test_init_help_names_every_flag_and_exits_zero(self, project: Path) -> None:
        run = Run(project)

        code = run.cli("init", "--help")

        assert code == 0
        for flag in (
            "--dry-run",
            "--write-existing",
            "--force",
            "--only",
            "--vendor",
            "--from",
            "--json",
        ):
            assert flag in run.stdout

    def test_init_help_says_how_an_installed_project_is_refreshed(self, project: Path) -> None:
        """This runtime has no refresh-on-build hook, so the help text is where a reader learns
        what does keep the pages current: re-running the verb, and the doctor's own report."""
        run = Run(project)

        run.cli("init", "--help")

        assert "Nothing refreshes the installed pages on a build" in run.stdout
        assert "Re-run this verb" in run.stdout
        assert "`narrativetrace doctor` reports when what is installed is stale." in run.stdout

    def test_uninstall_help_exits_zero_and_describes_the_verb(self, project: Path) -> None:
        run = Run(project)

        assert run.cli("uninstall", "-h") == 0
        assert "narrativetrace uninstall [options]" in run.stdout

    def test_uninstall_help_lists_only_the_flags_that_change_an_uninstall(
        self, project: Path
    ) -> None:
        """`plan_uninstall` reads only the scope, and the verb never opens a carrier — so the
        init-only flags are absent here, and the per-verb help agrees with the top-level synopsis
        instead of contradicting it."""
        run = Run(project)

        run.cli("uninstall", "--help")

        assert "--dry-run" in run.stdout
        assert "--only <half>" in run.stdout
        assert "--json" in run.stdout
        for init_only in ("--write-existing", "--force", "--vendor", "--from"):
            assert init_only not in run.stdout

    def test_both_verbs_say_what_a_preview_exits_with(self, project: Path) -> None:
        """A person deciding whether to trust `--dry-run` reads this sentence, so it is asserted
        word for word — and it says what is true: a preview of a REFUSAL still exits 0."""
        run = Run(project)

        run.cli("init", "--help")
        run.cli("uninstall", "--help")

        for shown in run.out:
            assert (
                "  --dry-run         Show the plan and the unified diff, and write nothing."
                " A refusal is shown\n                    rather than applied, so a preview of one"
                " still exits 0." in shown
            )
            assert (
                "Exit 0 = applied, or previewed; 1 = something was refused, or the project could"
                " not be read;\n2 = the command could not run at all." in shown
            )

    def test_help_wins_over_an_unreadable_flag_beside_it(self, project: Path) -> None:
        run = Run(project)

        assert run.cli("init", "--nope", "--help") == 0
        assert "narrativetrace init [options]" in run.stdout
        assert run.stderr == ""


class TestWhatCannotRun:
    def test_an_unknown_installer_flag_exits_two_with_the_verbs_usage(self, project: Path) -> None:
        run = Run(project)

        code = run.cli("init", "--nope")

        assert code == 2
        assert 'unknown option: "--nope"' in run.stderr
        assert "narrativetrace init [options]" in run.stderr
        assert files_under(project) == []

    def test_a_bad_flag_value_exits_two(self, project: Path) -> None:
        run = Run(project)

        code = run.cli("init", "--only", "everything")

        assert code == 2
        assert '--only takes skills or agents-md, got "everything"' in run.stderr

    def test_uninstall_reads_the_same_flags(self, project: Path) -> None:
        run = Run(project)

        assert run.cli("uninstall", "--nope") == 2
        assert "narrativetrace uninstall [options]" in run.stderr

    def test_a_carrier_that_cannot_be_opened_exits_one_and_says_what_to_do(
        self, project: Path
    ) -> None:
        run = Run(project, refusal="no carrier at nowhere.whl")

        code = run.cli("init", "--from", "nowhere.whl")

        assert code == 1
        assert "no carrier at nowhere.whl" in run.stderr
        assert "uv add narrativetrace-skills" in run.stderr
        assert "--from" in run.stderr
        assert files_under(project) == []

    def test_a_project_directory_that_is_not_one_exits_one(
        self, tmp_path: Path, carrier: Carrier
    ) -> None:
        """Exit 1, not 2: the command was typed correctly, it could not do the work."""
        run = Run(tmp_path / "gone", carrier)

        code = run.cli("init")

        assert code == 1
        assert "is not a directory" in run.stderr


class TestWhichCarrierIsAskedFor:
    def test_from_reaches_the_carrier_reader_verbatim(
        self, project: Path, carrier: Carrier
    ) -> None:
        run = Run(project, carrier)

        run.cli("init", "--from=some.whl", "--dry-run")

        assert run.asked_for == ["some.whl"]

    def test_no_from_asks_for_the_resolved_carrier(self, project: Path, carrier: Carrier) -> None:
        run = Run(project, carrier)

        run.cli("init", "--dry-run")

        assert run.asked_for == [None]

    def test_uninstall_never_opens_a_carrier(self, project: Path, carrier: Carrier) -> None:
        Run(project, carrier).cli("init")
        run = Run(project)

        assert run.cli("uninstall") == 0
        assert run.asked_for == []


class TestTheVersionGuard:
    def test_says_nothing_when_the_carrier_is_the_release_this_project_resolves(
        self, project: Path, carrier: Carrier
    ) -> None:
        run = Run(project, carrier)

        run.cli("init", "--dry-run", project_version=PROJECT_VERSION)

        assert run.stderr == ""

    def test_names_both_versions_on_a_mismatch_without_refusing(
        self, project: Path, carrier: Carrier
    ) -> None:
        run = Run(project, carrier)

        code = run.cli("init", project_version="9.9.9")

        assert code == 0
        assert CARRIER_COORDINATE in run.stderr
        assert "narrativetrace==9.9.9" in run.stderr
        assert agents_page(project).is_file()

    def test_says_nothing_when_the_project_resolves_no_release_at_all(
        self, project: Path, carrier: Carrier
    ) -> None:
        """The empty-project path the install prompt starts from: "cannot tell" is not a warning."""
        run = Run(project, carrier)

        run.cli("init", "--dry-run", project_version=None)

        assert run.stderr == ""

    def test_the_warning_leaves_the_json_on_stdout_machine_readable(
        self, project: Path, carrier: Carrier
    ) -> None:
        run = Run(project, carrier)

        run.cli("init", "--json", project_version="9.9.9")

        assert run.stderr != ""
        assert json.loads(run.out[0])["exit_code"] == 0

    def test_uninstall_never_warns_about_versions(self, project: Path, carrier: Carrier) -> None:
        Run(project, carrier).cli("init")
        run = Run(project)

        run.cli("uninstall", project_version="9.9.9")

        assert run.stderr == ""


class TestUninstall:
    def test_after_init_it_leaves_the_tree_byte_identical(
        self, project: Path, carrier: Carrier
    ) -> None:
        (project / "CLAUDE.md").write_text("# Claude\n", encoding="utf-8")
        (project / "README.md").write_text("# Read me\n", encoding="utf-8")
        before = tree(project)

        Run(project, carrier).cli("init", "--write-existing")
        code = Run(project).cli("uninstall")

        assert code == 0
        assert tree(project) == before

    def test_a_dry_run_removes_nothing(self, project: Path, carrier: Carrier) -> None:
        Run(project, carrier).cli("init")
        installed = tree(project)
        run = Run(project)

        code = run.cli("uninstall", "--dry-run")

        assert code == 0
        assert tree(project) == installed
        assert "-<!-- narrativetrace:start" in run.stdout

    def test_on_a_project_that_never_ran_init_it_does_nothing(self, project: Path) -> None:
        run = Run(project)

        code = run.cli("uninstall")

        assert code == 0
        assert "0 applied" in run.stdout
        assert files_under(project) == []

    def test_only_skills_leaves_the_section_behind(self, project: Path, carrier: Carrier) -> None:
        Run(project, carrier).cli("init")

        code = Run(project).cli("uninstall", "--only", "skills")

        assert code == 0
        assert not agents_page(project).exists()
        assert (project / "AGENTS.md").is_file()


class TestWhatAPreviewPromisesAndWhatItDoesNot:
    def test_a_preview_of_a_refusal_exits_zero(self, project: Path, carrier: Carrier) -> None:
        (project / "AGENTS.md").write_text("# Mine\n", encoding="utf-8")
        run = Run(project, carrier)

        code = run.cli("init", "--dry-run")

        assert code == 0
        assert "--write-existing" in run.stdout

    def test_a_preview_that_cannot_read_the_project_exits_one(
        self, tmp_path: Path, carrier: Carrier
    ) -> None:
        """Not a contradiction of the line above, and the help text now says which is which: a dry
        run's 0 covers every outcome of PLANNING. A project that cannot be read produced no plan, so
        reporting success would tell a script the run is safe to repeat for real when it is not.
        """
        run = Run(tmp_path / "gone", carrier)

        code = run.cli("init", "--dry-run")

        assert code == 1
        assert "is not a directory" in run.stderr
        assert run.stdout == ""

    def test_the_same_holds_for_uninstall(self, tmp_path: Path) -> None:
        run = Run(tmp_path / "gone")

        assert run.cli("uninstall", "--dry-run") == 1
        assert "is not a directory" in run.stderr


class TestFlagsThatDoNothingForUninstall:
    def test_the_init_only_flags_are_accepted_and_change_nothing(
        self, project: Path, carrier: Carrier
    ) -> None:
        """One argument reader serves both verbs, as in the Java port, so uninstall tolerates
        init's flags rather than refusing them — a caller passing the same flags to both commands is
        not doing anything wrong. What it must not do is act on them, or open a carrier."""
        Run(project, carrier).cli("init")
        plain = Run(project, carrier)
        plain.cli("uninstall", "--dry-run")

        loaded = Run(project)
        code = loaded.cli(
            "uninstall",
            "--dry-run",
            "--force",
            "--write-existing",
            "--vendor",
            "claude",
            "--from=x",
        )

        assert code == 0
        assert loaded.asked_for == []
        assert loaded.stdout == plain.stdout


class TestFlagCombinations:
    def test_the_vendor_flavour_lands_under_a_skills_only_install(
        self, project: Path, carrier: Carrier
    ) -> None:
        code = Run(project, carrier).cli("init", "--vendor", "claude", "--only", "skills")

        assert code == 0
        assert agents_page(project).is_file()
        assert (project / ".claude/skills" / SKILL / "SKILL.md").is_file()
        assert not (project / "AGENTS.md").exists()

    def test_a_skills_only_install_survives_an_agents_md_only_uninstall(
        self, project: Path, carrier: Carrier
    ) -> None:
        Run(project, carrier).cli("init", "--only", "skills")

        code = Run(project).cli("uninstall", "--only", "agents-md")

        assert code == 0
        assert agents_page(project).is_file()

    def test_every_permission_at_once_under_a_preview_still_writes_nothing(
        self, project: Path, carrier: Carrier
    ) -> None:
        run = Run(project, carrier)

        code = run.cli("init", "--dry-run", "--force", "--write-existing", "--json")

        assert code == 0
        assert files_under(project) == []
        assert json.loads(run.out[0])["exit_code"] == 0

    def test_a_usage_error_never_reaches_stdout_even_when_json_was_asked_for(
        self, project: Path
    ) -> None:
        """Whatever wraps this command parses stdout. A flag it could not read is a message for a
        person, on stderr, and must never arrive as half a JSON document."""
        run = Run(project)

        code = run.cli("init", "--json", "--nope")

        assert code == 2
        assert run.out == []
        assert "narrativetrace init [options]" in run.stderr


class TestWhenTheProjectChangesUnderTheRun:
    def test_a_project_that_vanishes_between_the_read_and_the_apply_exits_one(
        self, project: Path, carrier: Carrier, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The plan is computed from a snapshot, so the directory can stop being one before the
        executor reaches it — a concurrent cleanup, a `git clean`, a removed mount. That must be the
        same one-line exit 1 every other unreadable-project case gets, never a traceback: `main`
        promises an exit code, and an escaping exception is not one.

        The race is forced rather than waited for: the reader is wrapped so the directory is removed
        the instant the snapshot has been taken, which is exactly the window under test.
        """

        def read_then_vanish(directory: Path) -> ProjectState:
            state = read_project_state(directory)
            shutil.rmtree(directory)
            return state

        monkeypatch.setattr(cli_bin, "read_project_state", read_then_vanish)
        run = Run(project, carrier)

        code = run.cli("init")

        assert code == 1
        assert "is not a directory" in run.stderr
        assert run.stdout == ""


class TestTheRealProcessWiring:
    """`main`'s own dependencies — the real carrier resolution and the real streams, not the
    injected fakes every case above uses.

    The scratch project is this test's own `tempfile.mkdtemp()` and is passed to `main`'s explicit
    `cwd`, never patched onto the process: see `test_doctor_cli_bin.py`'s note for why both of those
    matter under the mutation gate.
    """

    def test_a_dry_run_plans_an_install_from_the_carrier_this_repository_resolves(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        scratch = Path(tempfile.mkdtemp(prefix="narrativetrace-init-cli-"))
        try:
            exit_code = main(["init", "--dry-run"], cwd=str(scratch))

            shown = capsys.readouterr().out
            assert exit_code == 0
            assert "+++ b/AGENTS.md" in shown
            assert "installed by narrativetrace init from narrativetrace" in shown
            assert files_under(scratch) == []
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_the_project_it_reads_is_the_one_it_was_given(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`main`'s `cwd` argument, pinned by naming a directory that does not exist: the refusal
        quotes the path it actually looked at, so falling back to the process cwd (which does
        exist) could not produce this message at all."""
        scratch = Path(tempfile.mkdtemp(prefix="narrativetrace-init-cli-"))
        missing = scratch / "gone"
        try:
            exit_code = main(["init", "--dry-run"], cwd=str(missing))

            assert exit_code == 1
            assert f"{missing} is not a directory" in capsys.readouterr().err
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_with_no_argv_it_reads_the_processs_own(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The console script passes nothing: `main` takes the arguments after the program name off
        `sys.argv` itself. `cwd` is still given explicitly, so this test never depends on where the
        process happens to be (see `test_doctor_cli_bin.py`'s note on that hazard)."""
        monkeypatch.setattr(sys, "argv", ["narrativetrace", "frobnicate"])

        exit_code = main(cwd="/nonexistent-for-this-test")

        assert exit_code == 2
        assert "Unknown command: frobnicate" in capsys.readouterr().err

    def test_a_named_carrier_that_is_not_there_exits_one_on_real_stderr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        scratch = Path(tempfile.mkdtemp(prefix="narrativetrace-init-cli-"))
        try:
            exit_code = main(["init", "--from", str(scratch / "nope")], cwd=str(scratch))

            assert exit_code == 1
            assert "no carrier at" in capsys.readouterr().err
            assert files_under(scratch) == []
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
