# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Shared snapshot factory for doctor check tests — every check is a pure function over a
:class:`~narrativetrace.doctor.types.DoctorSnapshot`, so its tests build one directly rather than
touching the real filesystem or installed-package metadata."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from narrativetrace.doctor.types import DoctorSnapshot, PackageInfo


@pytest.fixture
def make_snapshot():
    def _make(
        *,
        cwd: str = "/project",
        python_version: str = "3.12.4",
        env: Mapping[str, str] | None = None,
        root_pyproject: Mapping[str, object] | None = None,
        narrativetrace_config: Mapping[str, object] | None = None,
        source_files: Mapping[str, str] | None = None,
        output_files: Mapping[str, str] | None = None,
        approved_dir_files: Mapping[str, str] | None = None,
        installed_packages: Mapping[str, PackageInfo] | None = None,
        pytest11_entry_points: Mapping[str, str] | None = None,
    ) -> DoctorSnapshot:
        return DoctorSnapshot(
            cwd=cwd,
            python_version=python_version,
            env=env or {},
            root_pyproject=root_pyproject if root_pyproject is not None else {"project": {}},
            narrativetrace_config=narrativetrace_config or {},
            source_files=source_files or {},
            output_files=output_files or {},
            approved_dir_files=approved_dir_files or {},
            installed_packages=installed_packages or {},
            pytest11_entry_points=pytest11_entry_points or {},
        )

    return _make


@pytest.fixture
def package_info():
    def _make(
        name: str, version: str, requires_python: str | None = None, requires: tuple[str, ...] = ()
    ) -> PackageInfo:
        return PackageInfo(
            name=name, version=version, requires_python=requires_python, requires=requires
        )

    return _make
