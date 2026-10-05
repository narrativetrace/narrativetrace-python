# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The version guard the Java port does not need: this runtime's CLI and its skills carrier are two
distributions, so a project can resolve one of them at a version the other does not match.

A warning, never a refusal, and silent where there is nothing to tell — the rules the design set.
"""

from __future__ import annotations

import tomllib
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

import carriers
import pytest

from narrativetrace_tooling.init.carrier import CORE_DISTRIBUTION, Carrier, resolve_carrier
from narrativetrace_tooling.init.version_guard import project_family_version, version_warning

MISSING: Any = None


def repo_version() -> str:
    metadata: dict[str, Any] = tomllib.loads(
        (carriers.repo_root() / "pyproject.toml").read_text(encoding="utf-8")
    )
    return str(metadata["project"]["version"])


@pytest.fixture
def carrier(tmp_path: Path) -> Carrier:
    """A carrier stamped ``narrativetrace-skills==1.2.3`` — deliberately not this repo's version."""
    return carriers.fake(tmp_path, "doctor")


class TestWhatTheProjectResolves:
    def test_reads_the_release_this_project_resolves(self) -> None:
        assert project_family_version() == repo_version()

    def test_reads_none_in_a_directory_that_resolves_no_narrativetrace_at_all(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The empty-project answer. Injected rather than staged in a scratch venv: the branch is
        about a distribution that is not installed, and this test's own interpreter has it."""

        def not_installed(_: str) -> str:
            raise importlib_metadata.PackageNotFoundError(CORE_DISTRIBUTION)

        monkeypatch.setattr(importlib_metadata, "version", not_installed)

        assert project_family_version() is None


class TestWhenItWarns:
    def test_names_both_versions_and_the_command_that_lines_them_up(self, carrier: Carrier) -> None:
        warning = version_warning(carrier, "0.9.9")

        assert warning is not None
        assert "narrativetrace-skills==1.2.3" in warning
        assert f"{CORE_DISTRIBUTION}==0.9.9" in warning
        assert "uv add 'narrativetrace-skills==0.9.9'" in warning
        assert "\n" not in warning, "one line, so a caller can print it beside the plan"

    def test_warns_about_a_carrier_that_cannot_say_which_version_it_is(self) -> None:
        """``unknown`` is the honest stamp of a carrier read out of a directory that names no
        version — and "I cannot tell whether these pages match" is what a reader needs to hear."""
        warning = version_warning(carriers.real(), "0.9.9")

        assert warning is not None
        assert "skills==unknown" in warning

    def test_is_a_warning_and_never_a_refusal(self, carrier: Carrier) -> None:
        """Nothing here raises: refusing would block the empty-project path the install prompt
        serves, and the doctor's own staleness finding catches the result either way."""
        assert version_warning(carrier, "0.9.9") is not None
        assert version_warning(carrier, "1.2.3") is None


class TestWhenItSaysNothing:
    def test_says_nothing_when_the_versions_match(self, carrier: Carrier) -> None:
        assert version_warning(carrier, "1.2.3") is None

    def test_says_nothing_when_the_project_resolves_no_version_at_all(
        self, carrier: Carrier
    ) -> None:
        assert version_warning(carrier, None) is None

    def test_says_nothing_about_this_repositorys_own_resolved_carrier(self) -> None:
        """The ordinary case, end to end: the carrier this project resolves and the release it runs
        are the same, so an install in this repository prints no warning."""
        assert version_warning(resolve_carrier(), project_family_version()) is None


class TestGuards:
    def test_refuses_to_compare_without_a_carrier(self) -> None:
        with pytest.raises(TypeError, match=r"a carrier is needed"):
            version_warning(MISSING, "1.2.3")
