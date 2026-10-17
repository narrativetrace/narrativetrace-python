# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier A2 for the install skill, from ZERO (B-87). The page used to be replayed only in
``examples/sixty_seconds``, a workspace member that already has every NarrativeTrace package -- the
one project where "the page never adds the package" cannot show. Here the skill's own fixture (an
empty project) is copied OUTSIDE the repository and the page runs in it as a reader would: this
checkout's built wheels reach the page's own ``uv add`` through a find-links source (the one
mechanism the Tier B runner uses, ``evals/run.py``'s ``_FIND_LINKS_VARIABLE``), and a snippet
step's file is saved into the project before its verify runs.

The replay's ``uv`` is isolated from this workspace: the project lives in a scratch directory with
no parent project, so ``uv`` cannot read or rewrite this repository's lockfile; the cache is
private, so a published release cached under the same version cannot stand in for the build.

The budget guards a hang, not a figure (``scripts.timeout_floor``): building the wheels and the
whole replay are measured in the module's closing note, 2026-10-16, dev container.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest
from narrativetrace_skills.catalogue.add_narrative_tracing import ADD_NARRATIVE_TRACING
from narrativetrace_skills.replay import StepReplayResult, replay_skill
from narrativetrace_skills.skill import SnippetStep

_REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "uv.lock").is_file())
_EMPTY_PROJECT = (
    _REPO_ROOT / "packages/narrativetrace-skills-catalogue/evals/fixtures/empty-project"
)
_FIND_LINKS_VARIABLE = "UV_FIND_LINKS"
_INHERITED_UV_SETTINGS = ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "UV_CACHE_DIR")


def _reader_environment(scratch: Path, wheels: Path) -> dict[str, str]:
    """The environment a reader's own shell has: none of this session's virtual environment, a
    private uv cache, and this checkout's wheels as the only package source.

    ``UV_NO_INDEX`` because a find-links source alone does not win against an index that serves the
    SAME version: once 0.4.0 was published, the lock recorded PyPI's wheel, not this build's
    (2026-10-16). ``narrativetrace``'s whole dependency closure is workspace wheels, so nothing
    needs the index."""
    env = {k: v for k, v in os.environ.items() if k not in _INHERITED_UV_SETTINGS}
    env["UV_CACHE_DIR"] = str(scratch / "uv-cache")
    env[_FIND_LINKS_VARIABLE] = str(wheels)
    env["UV_NO_INDEX"] = "1"
    return env


def _save_snippet(snippet: SnippetStep, cwd: str) -> None:
    """The reader saving the shown file into the project, under its own name."""
    source = _REPO_ROOT / snippet.path
    shutil.copy(source, Path(cwd) / source.name)


_ColdReplay = tuple[Path, tuple[StepReplayResult, ...]]
"""The project directory the page ran in, and each step's result."""


@pytest.fixture(scope="module")
def cold_replay(tmp_path_factory: pytest.TempPathFactory) -> Iterator[_ColdReplay]:
    scratch = tmp_path_factory.mktemp("nt-cold-install")
    project, wheels = scratch / "project", scratch / "wheels"
    shutil.copytree(_EMPTY_PROJECT, project)
    subprocess.run(  # nosec B603, B607 - fixed uv invocation, this checkout's own build
        ["uv", "build", "--wheel", "--all-packages", "-o", str(wheels)],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
    )
    env = _reader_environment(scratch, wheels)

    def run(command: str, cwd: str) -> None:
        subprocess.run(command, shell=True, cwd=cwd, capture_output=True, check=True, env=env)  # nosec B602 - the catalogue's own typed commands

    yield project, replay_skill(ADD_NARRATIVE_TRACING, str(project), run, _save_snippet)


def test_the_fixture_starts_from_zero_no_dependency_no_lockfile_no_environment() -> None:
    """A replay run IN the checked-in fixture once left a dependency, a ``uv.lock`` and a ``.venv``
    behind (2026-10-16); the cold replay works on a copy, and this keeps the original bare."""
    manifest = tomllib.loads((_EMPTY_PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    assert manifest["project"]["dependencies"] == []
    assert sorted(p.name for p in _EMPTY_PROJECT.iterdir()) == ["README.md", "pyproject.toml"]


@pytest.mark.timeout(600)
def test_every_step_of_the_page_succeeds_from_an_empty_project(cold_replay: _ColdReplay) -> None:
    _, results = cold_replay
    failing = [r for r in results if not r.ok]
    assert failing == [], failing


@pytest.mark.timeout(600)
def test_the_project_ends_declaring_narrativetrace_it_added_itself(
    cold_replay: _ColdReplay,
) -> None:
    project, _ = cold_replay
    declared = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert [d.split(">")[0].split("=")[0] for d in declared["dependencies"]] == ["narrativetrace"]


@pytest.mark.timeout(600)
def test_narrativetrace_came_from_this_checkouts_wheels_not_a_published_release(
    cold_replay: _ColdReplay,
) -> None:
    project, _ = cold_replay
    lock = tomllib.loads((project / "uv.lock").read_text(encoding="utf-8"))
    [package] = [p for p in lock["package"] if p["name"] == "narrativetrace"]
    # uv writes the find-links registry as an absolute path in one version and relative to the
    # lockfile in another (CI, 2026-10-17); resolve before comparing so neither form is a failure.
    [registry] = package["source"].values()
    assert (project / registry).resolve() == (project.parent / "wheels").resolve()


def test_the_replay_never_touches_this_repositorys_lockfile(cold_replay: _ColdReplay) -> None:
    status = subprocess.run(  # nosec B603, B607 - fixed git query
        ["git", "status", "--porcelain", "--", "uv.lock"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert status.stdout == ""
