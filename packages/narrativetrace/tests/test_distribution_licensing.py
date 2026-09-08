# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Every distribution must ship the licence text, in-tree and in the built artifacts.

BSL 1.1 requires the licence to be displayed on *every copy* of the Licensed Work, so an artifact
without it is not publishable. `license = "BUSL-1.1"` only stamps the expression: until 2026-08-31
the eight wheels carried `License-Expression: BUSL-1.1` and no licence file at all, because
hatchling resolves `license-files` inside each `packages/<dist>/` and the LICENSE lived only at the
repo root. PEP 639 forbids `..` in `license-files`, so the fix is one byte-identical copy per
distribution — and copies rot silently, which is what this module exists to prevent.

Two layers, deliberately: the static checks pin the configuration that produces a correct artifact,
and :class:`TestEveryBuiltArtifact` builds the artifacts and reads the licence back out of them, so
the gate fails on the wheel itself rather than on a proxy for it. Discovery runs off the root
pyproject's own workspace glob, so a ninth distribution is swept in the moment it is added rather
than quietly skipped.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any, NamedTuple

import pytest


def _repo_root() -> Path:
    """The workspace root, found by walking up rather than by counting directories.

    mutmut runs this suite from a `packages/narrativetrace/mutants/` copy, one level deeper than
    the source tree, so a fixed `parents[3]` would resolve to `packages/` there and fail at import
    — which kills collection for the whole mutation run.
    """
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


REPO_ROOT = _repo_root()
ROOT_LICENSE = REPO_ROOT / "LICENSE"


def _read_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _distributions() -> list[Path]:
    """Every workspace member directory, resolved from the root pyproject's own glob."""
    members: list[str] = _read_toml(REPO_ROOT / "pyproject.toml")["tool"]["uv"]["workspace"][
        "members"
    ]
    found = {
        match
        for member in members
        for match in REPO_ROOT.glob(member)
        if (match / "pyproject.toml").is_file()
    }
    return sorted(found)


DISTRIBUTIONS = _distributions()
DISTRIBUTION_IDS = [path.name for path in DISTRIBUTIONS]


class _Artifacts(NamedTuple):
    """The exact filenames `uv build` produces for one distribution.

    Named in full rather than globbed: a glob passes when some *other* distribution's wheel is the
    only thing in the directory and the one under test was never built.
    """

    wheel: str
    sdist: str
    dist_info: str
    sdist_root: str


def _artifacts_of(distribution: Path) -> _Artifacts:
    project = _read_toml(distribution / "pyproject.toml")["project"]
    canonical = re.sub(r"[-_.]+", "_", str(project["name"])).lower()
    stem = f"{canonical}-{project['version']}"
    return _Artifacts(f"{stem}-py3-none-any.whl", f"{stem}.tar.gz", f"{stem}.dist-info", stem)


@pytest.fixture(scope="session")
def built_distributions(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Builds every distribution once, exactly as a release would, into a throwaway directory."""
    if shutil.which("uv") is None:
        pytest.skip("uv is not on PATH, so the built artifacts cannot be inspected")
    out_dir = tmp_path_factory.mktemp("built-distributions")
    build = subprocess.run(  # nosec B603, B607 # fixed argv, no shell, no untrusted input
        ["uv", "build", "--all-packages", "--out-dir", str(out_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, f"uv build failed:\n{build.stdout}\n{build.stderr}"
    return out_dir


class TestTheLicenceTheDistributionsCopy:
    def test_the_root_licence_is_the_business_source_licence(self) -> None:
        text = ROOT_LICENSE.read_text(encoding="utf-8")
        assert text.startswith("Business Source License 1.1")
        assert "Licensor:             Empower Agile" in text

    def test_the_sweep_finds_the_workspace_distributions(self) -> None:
        assert "narrativetrace" in DISTRIBUTION_IDS


@pytest.mark.parametrize("distribution", DISTRIBUTIONS, ids=DISTRIBUTION_IDS)
class TestEveryDistribution:
    def test_carries_a_licence_byte_identical_to_the_root_one(self, distribution: Path) -> None:
        assert (distribution / "LICENSE").read_bytes() == ROOT_LICENSE.read_bytes()

    def test_declares_the_licence_expression_the_owner_fixed(self, distribution: Path) -> None:
        project = _read_toml(distribution / "pyproject.toml")["project"]
        assert project["license"] == "BUSL-1.1"

    def test_tells_the_build_backend_to_ship_that_licence(self, distribution: Path) -> None:
        project = _read_toml(distribution / "pyproject.toml")["project"]
        assert project["license-files"] == ["LICENSE"]


@pytest.mark.parametrize("distribution", DISTRIBUTIONS, ids=DISTRIBUTION_IDS)
class TestEveryBuiltArtifact:
    """Reads the licence back out of the artifacts, so the gate cannot pass on intent alone."""

    def test_the_wheel_contains_the_licence_text(
        self, distribution: Path, built_distributions: Path
    ) -> None:
        artifacts = _artifacts_of(distribution)
        with zipfile.ZipFile(built_distributions / artifacts.wheel) as wheel:
            licence = f"{artifacts.dist_info}/licenses/LICENSE"
            assert licence in wheel.namelist()
            assert wheel.read(licence) == ROOT_LICENSE.read_bytes()

    def test_the_wheel_metadata_records_the_licence(
        self, distribution: Path, built_distributions: Path
    ) -> None:
        artifacts = _artifacts_of(distribution)
        with zipfile.ZipFile(built_distributions / artifacts.wheel) as wheel:
            headers = wheel.read(f"{artifacts.dist_info}/METADATA").decode("utf-8").splitlines()
        assert "License-Expression: BUSL-1.1" in headers
        assert "License-File: LICENSE" in headers

    def test_the_sdist_contains_the_licence_text(
        self, distribution: Path, built_distributions: Path
    ) -> None:
        artifacts = _artifacts_of(distribution)
        with tarfile.open(built_distributions / artifacts.sdist) as sdist:
            licence = f"{artifacts.sdist_root}/LICENSE"
            assert licence in sdist.getnames()
            carried = sdist.extractfile(licence)
            assert carried is not None
            assert carried.read() == ROOT_LICENSE.read_bytes()
