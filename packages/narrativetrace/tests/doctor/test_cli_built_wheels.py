# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Proves the `narrativetrace` console script works from the REAL wheels, by installing them into a
throwaway virtual environment and running it (Java's `CliExecutableJarTest`, ported).

Two failure modes live here and nowhere else. The carrier is a PACKAGE-DATA promise: a wheel whose
`narrativetrace/_skills/**` was not packaged — or a launcher that looks for the payload somewhere
`importlib.metadata` cannot see once installed — passes every unit test in this repository and fails
the first time a consumer types the command. And the installer library is a SEPARATE distribution
since the tooling split, which is exactly the shape that turns an advertised entry point into an
`ImportError` nobody notices until a release.

So each case here runs the script the way a person does: `narrativetrace init --dry-run` from a real
venv, in a project directory that starts empty. The preference order (D1/D4) is asserted against two
real installs, because that is the one claim a fixture carrier can never make: with
`narrativetrace-skills` installed the pages come from it, and without it they come from the copy the
core distribution bundles.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from wheel_support import consumer_environment, wheel_name

CORE = "narrativetrace"

TOOLING = "narrativetrace-tooling"

SKILLS = "narrativetrace-skills"

SKILL = "narrativetrace-doctor"


@dataclass(frozen=True, slots=True)
class Installed:
    """A venv the built wheels were installed into, and the console script inside it."""

    script: Path
    version: str

    def run(self, project: Path, *argv: str) -> subprocess.CompletedProcess[str]:
        """Runs the console script with `project` as its working directory."""
        return subprocess.run(  # nosec B603 # fixed argv, no shell, no untrusted input
            [str(self.script), *argv],
            cwd=project,
            env=consumer_environment(),
            capture_output=True,
            text=True,
            check=False,
        )


def _install(venv: Path, wheels: Path, distributions: list[str]) -> Installed:
    """Makes a venv and installs exactly the named distributions' built wheels into it.

    `--offline` is not politeness: this asserts the wheels on disk are sufficient, so a missing
    dependency fails here instead of being silently downloaded from an index.
    """
    if shutil.which("uv") is None:
        pytest.skip("uv is not on PATH, so the built wheels cannot be installed")
    files = [str(wheels / wheel_name(distribution)) for distribution in distributions]
    for step in (["uv", "venv", str(venv)], ["uv", "pip", "install", "--offline", *files]):
        done = subprocess.run(  # nosec B603, B607 # fixed argv, no shell, no untrusted input
            [*step, *(["--python", str(venv)] if step[1] == "pip" else [])],
            env=consumer_environment(),
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, f"{' '.join(step)} failed:\n{done.stdout}\n{done.stderr}"
    return Installed(venv / "bin" / "narrativetrace", _built_version())


def _built_version() -> str:
    """The release these wheels were built at, read off the core wheel's own file name."""
    return wheel_name(CORE).split("-")[1]


@pytest.fixture(scope="session")
def bundled_only(tmp_path_factory: pytest.TempPathFactory, built_wheels: Path) -> Installed:
    """A consumer who only ran `uv add narrativetrace`: the carrier is the bundled copy."""
    return _install(tmp_path_factory.mktemp("venv-bundled"), built_wheels, [CORE, TOOLING])


@pytest.fixture(scope="session")
def with_skills_distribution(
    tmp_path_factory: pytest.TempPathFactory, built_wheels: Path
) -> Installed:
    """A consumer who also added `narrativetrace-skills`: that carrier wins."""
    return _install(tmp_path_factory.mktemp("venv-skills"), built_wheels, [CORE, TOOLING, SKILLS])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    directory = tmp_path / "project"
    directory.mkdir()
    return directory


def files_under(project: Path) -> list[str]:
    return sorted(str(file.relative_to(project)) for file in project.rglob("*") if file.is_file())


@pytest.mark.distribution
class TestTheInstalledConsoleScript:
    def test_its_usage_lists_every_verb_and_exits_zero(
        self, bundled_only: Installed, project: Path
    ) -> None:
        done = bundled_only.run(project, "--help")

        assert done.returncode == 0
        assert "narrativetrace init" in done.stdout
        assert "narrativetrace uninstall" in done.stdout

    def test_the_doctor_verb_still_reaches_its_own_distribution(
        self, bundled_only: Installed, project: Path
    ) -> None:
        """The doctor's checks live in `narrativetrace-tooling`; nothing but a real install proves
        the console script can still reach them. Exit 0 or 1 are both ordinary outcomes on a project
        this small; exit 2 would mean it could not run at all."""
        (project / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")

        done = bundled_only.run(project, "doctor", "--json")

        assert done.returncode in (0, 1), done.stderr
        assert '"findings"' in done.stdout


@pytest.mark.distribution
class TestInitFromTheCarrierTheCoreWheelBundles:
    def test_a_dry_run_plans_the_install_and_writes_nothing(
        self, bundled_only: Installed, project: Path
    ) -> None:
        coordinate = f"{CORE}=={bundled_only.version}"

        done = bundled_only.run(project, "init", "--dry-run")

        assert done.returncode == 0, done.stderr
        assert f"narrativetrace — {coordinate}" in done.stdout
        assert "+++ b/AGENTS.md" in done.stdout
        assert f"+++ b/.agents/skills/{SKILL}/SKILL.md" in done.stdout
        assert f"installed by narrativetrace init from {coordinate}" in done.stdout
        assert files_under(project) == []

    def test_the_json_envelope_comes_out_of_the_installed_script(
        self, bundled_only: Installed, project: Path
    ) -> None:
        done = bundled_only.run(project, "init", "--dry-run", "--json")

        assert done.returncode == 0, done.stderr
        assert f'"carrier": "{CORE}=={bundled_only.version}"' in done.stdout
        assert '"status": "planned"' in done.stdout
        assert '"exit_code": 0' in done.stdout

    def test_applying_it_writes_the_bundled_pages_and_uninstall_takes_them_back(
        self, bundled_only: Installed, project: Path
    ) -> None:
        applied = bundled_only.run(project, "init")

        assert applied.returncode == 0, applied.stderr
        page = project / ".agents/skills" / SKILL / "SKILL.md"
        assert f"name: {SKILL}" in page.read_text(encoding="utf-8")
        assert "<!-- narrativetrace:start " in (project / "AGENTS.md").read_text(encoding="utf-8")

        removed = bundled_only.run(project, "uninstall")

        assert removed.returncode == 0, removed.stderr
        assert files_under(project) == []


@pytest.mark.distribution
class TestInitPrefersTheCarrierTheProjectResolves:
    def test_the_skills_distribution_wins_over_the_bundled_copy(
        self, with_skills_distribution: Installed, project: Path
    ) -> None:
        done = with_skills_distribution.run(project, "init", "--dry-run")

        assert done.returncode == 0, done.stderr
        version = with_skills_distribution.version
        assert f"narrativetrace — {SKILLS}=={version}" in done.stdout
        assert f"installed by narrativetrace init from {SKILLS}=={version}" in done.stdout

    def test_the_two_carriers_install_the_same_page(
        self, bundled_only: Installed, with_skills_distribution: Installed, tmp_path: Path
    ) -> None:
        """The bundled copy and the published carrier are byte-identical by construction (milestone
        1 asserts that inside the wheels); through the CLI the pages differ only in the stamp."""
        pages: list[str] = []
        for installed in (bundled_only, with_skills_distribution):
            project = tmp_path / f"project-{len(pages)}"
            project.mkdir()
            installed.run(project, "init", "--only", "skills")
            pages.append((project / ".agents/skills" / SKILL / "SKILL.md").read_text("utf-8"))

        provenance = "<!-- installed by narrativetrace init from "
        assert pages[0].split(provenance)[0] == pages[1].split(provenance)[0]
        assert pages[0] != pages[1]


@pytest.mark.distribution
class TestWhatTheInstalledScriptRefuses:
    def test_a_named_carrier_that_is_not_there_exits_one(
        self, bundled_only: Installed, project: Path
    ) -> None:
        done = bundled_only.run(project, "init", "--from", str(project / "nowhere.whl"))

        assert done.returncode == 1
        assert "no carrier at" in done.stderr
        assert f"uv add {SKILLS}" in done.stderr
        assert files_under(project) == []

    def test_an_unreadable_flag_exits_two(self, bundled_only: Installed, project: Path) -> None:
        done = bundled_only.run(project, "init", "--only", "everything")

        assert done.returncode == 2
        assert "--only takes skills or agents-md" in done.stderr
