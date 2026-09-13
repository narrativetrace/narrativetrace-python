# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``config.pytest-plugin-registered`` — ``narrativetrace-pytest`` registers itself as a pytest
plugin via the ``pytest11`` entry point (``[project.entry-points.pytest11] narrativetrace =
"narrativetrace_pytest.plugin"``) the moment the distribution is installed, no config required.
Two ways that silently fails: the entry point resolves to something else (a broken/partial
install), or the project's own ``addopts`` disables it with ``-p no:narrativetrace``."""

from __future__ import annotations

import re

from narrativetrace.doctor.doc_urls import DOC
from narrativetrace.doctor.finding import failed, passed
from narrativetrace.doctor.types import DoctorSnapshot, Finding

ID = "config.pytest-plugin-registered"
_ENTRY_POINT_NAME = "narrativetrace"
_EXPECTED_MODULE = "narrativetrace_pytest.plugin"
_DISABLE_FLAG = re.compile(r"-p\s+no:narrativetrace\b")
_CONFIG_FILENAMES = frozenset({"pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini"})


def _addopts_disables_plugin(snapshot: DoctorSnapshot) -> str | None:
    for path, content in snapshot.source_files.items():
        if path in _CONFIG_FILENAMES and _DISABLE_FLAG.search(content):
            return path
    return None


def _entry_point_missing() -> Finding:
    return failed(
        ID,
        f"narrativetrace-pytest is installed but no {_ENTRY_POINT_NAME!r} pytest11 entry point "
        "was found",
        "Reinstall narrativetrace-pytest (`uv sync`) — a missing entry point means the wheel's "
        "metadata is broken or the environment resolved a stale install.",
        DOC["pytest_configuration"],
    )


def _entry_point_wrong(actual: str) -> Finding:
    return failed(
        ID,
        f"the {_ENTRY_POINT_NAME!r} pytest11 entry point resolves to {actual!r}, not "
        f"{_EXPECTED_MODULE!r}",
        "Something else on sys.path shadows narrativetrace-pytest's own entry point — check for a "
        "stray local module or a conflicting package named narrativetrace_pytest.",
        DOC["pytest_configuration"],
    )


def check_pytest_plugin_registered(snapshot: DoctorSnapshot) -> Finding:
    if "narrativetrace-pytest" not in snapshot.installed_packages:
        return passed(
            ID,
            "narrativetrace-pytest is not installed — nothing to check",
            DOC["pytest_configuration"],
        )
    actual = snapshot.pytest11_entry_points.get(_ENTRY_POINT_NAME)
    if actual is None:
        return _entry_point_missing()
    if actual != _EXPECTED_MODULE:
        return _entry_point_wrong(actual)
    disabling_file = _addopts_disables_plugin(snapshot)
    if disabling_file is not None:
        return failed(
            ID,
            f"{disabling_file} disables the plugin with `-p no:narrativetrace` in its addopts",
            "Remove `-p no:narrativetrace` from addopts, or scope it to the specific test run "
            "that needs the outer coverage tracer to see narrativetrace imports first (this "
            "repo's own conftest does exactly that for its own suite).",
            DOC["pytest_configuration"],
        )
    return passed(
        ID,
        "narrativetrace-pytest's pytest11 entry point is registered the documented way and is not "
        "disabled by addopts",
        DOC["pytest_configuration"],
    )
