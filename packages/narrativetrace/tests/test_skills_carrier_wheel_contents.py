# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Proves the CARRIER is inside the real wheels, not just in the source tree (Java's
`SkillsCarrierJarTest`, ported -- Phase 3 milestone 1).

What an installer unpacks is a wheel, so this test opens the real archives `uv build` produces
rather than reading the source tree back -- a fixture wheel assembled by the test would prove only
that the test can build one. Two wheels, because the carrier ships twice on purpose (D1):
`narrativetrace-skills` is the carrier a project resolves as an ordinary dependency, and
`narrativetrace` bundles an identical copy as package data so `init` works without that
distribution installed. "Identical" is asserted byte-for-byte here: two copies that could drift
are two carriers.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest
from wheel_support import wheel_name as _wheel_name

# The carrier's root inside the standalone wheel vs. inside narrativetrace's own package data --
# mirrors RenderPaths.CARRIER_JAR_ROOT's two homes in the Java port.
CARRIER_ROOT = "skills/"
BUNDLED_ROOT = "narrativetrace/_skills/"

CARRIER_RELATIVE_ENTRIES = [
    "catalogue.json",
    "agents/narrativetrace-doctor/SKILL.md",
    "agents/add-narrative-tracing/SKILL.md",
    "agents/narrativetrace-feedback/SKILL.md",
    "agents/add-narrativetrace-clarity/SKILL.md",
    "agents/narrativetrace-verify/SKILL.md",
    "agents/narrativetrace-debug/SKILL.md",
    "claude/narrativetrace-doctor/SKILL.md",
    "claude/add-narrative-tracing/SKILL.md",
    "claude/narrativetrace-feedback/SKILL.md",
    "claude/add-narrativetrace-clarity/SKILL.md",
    "claude/narrativetrace-verify/SKILL.md",
    "claude/narrativetrace-debug/SKILL.md",
]


def _entry_names(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as zf:
        return [name for name in zf.namelist() if not name.endswith("/")]


def _entry_text(wheel: Path, name: str) -> str:
    with zipfile.ZipFile(wheel) as zf:
        assert name in zf.namelist(), f"{name} missing from {wheel.name}"
        return zf.read(name).decode("utf-8")


@pytest.mark.distribution
class TestTheCarrierWheel:
    def test_carries_the_nine_carrier_entries(self, built_wheels: Path) -> None:
        wheel = built_wheels / _wheel_name("narrativetrace-skills")
        names = _entry_names(wheel)
        assert all(f"{CARRIER_ROOT}{relative}" in names for relative in CARRIER_RELATIVE_ENTRIES)

    def test_carries_no_python_source(self, built_wheels: Path) -> None:
        wheel = built_wheels / _wheel_name("narrativetrace-skills")
        assert [name for name in _entry_names(wheel) if name.endswith(".py")] == []

    def test_carries_nothing_under_the_carrier_root_beyond_the_nine_entries(
        self, built_wheels: Path
    ) -> None:
        wheel = built_wheels / _wheel_name("narrativetrace-skills")
        under_root = [name for name in _entry_names(wheel) if name.startswith(CARRIER_ROOT)]
        assert sorted(under_root) == sorted(f"{CARRIER_ROOT}{r}" for r in CARRIER_RELATIVE_ENTRIES)


@pytest.mark.distribution
class TestTheCoreWheelBundlesTheSameCarrier:
    def test_carries_the_same_nine_entries_byte_for_byte(self, built_wheels: Path) -> None:
        skills_wheel = built_wheels / _wheel_name("narrativetrace-skills")
        core_wheel = built_wheels / _wheel_name("narrativetrace")
        for relative in CARRIER_RELATIVE_ENTRIES:
            carrier_text = _entry_text(skills_wheel, f"{CARRIER_ROOT}{relative}")
            bundled_text = _entry_text(core_wheel, f"{BUNDLED_ROOT}{relative}")
            assert bundled_text == carrier_text

    def test_still_carries_its_own_python_source(self, built_wheels: Path) -> None:
        wheel = built_wheels / _wheel_name("narrativetrace")
        names = _entry_names(wheel)
        assert "narrativetrace/__init__.py" in names
        assert "narrativetrace/cli.py" in names


@pytest.mark.distribution
class TestTheCatalogueManifestItself:
    def test_names_every_skill_exactly_once_and_points_at_entries_that_exist(
        self, built_wheels: Path
    ) -> None:
        wheel = built_wheels / _wheel_name("narrativetrace-skills")
        catalogue = _entry_text(wheel, f"{CARRIER_ROOT}catalogue.json")
        names = re.findall(r'"name": "([^"]+)"', catalogue)
        assert sorted(names) == sorted(
            [
                "narrativetrace-doctor",
                "add-narrative-tracing",
                "narrativetrace-feedback",
                "add-narrativetrace-clarity",
                "narrativetrace-verify",
                "narrativetrace-debug",
            ]
        )

        entry_names = _entry_names(wheel)
        for relative in re.findall(r'"(?:agents|claude)": "([^"]+)"', catalogue):
            assert f"{CARRIER_ROOT}{relative}" in entry_names

    def test_carries_no_version_literal(self, built_wheels: Path) -> None:
        wheel = built_wheels / _wheel_name("narrativetrace-skills")
        catalogue = _entry_text(wheel, f"{CARRIER_ROOT}catalogue.json")
        assert re.search(r"\d+\.\d+\.\d+", catalogue) is None
