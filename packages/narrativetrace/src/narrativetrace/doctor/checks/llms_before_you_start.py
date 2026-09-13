# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``trap.llms-before-you-start`` — ``llms.txt``'s own "Before you start" trap for
``narrativetrace-structlog``: on PyPI's published ``0.1.1``, ``structlog`` is an optional extra a
consumer must add explicitly (``uv add structlog``); importing ``narrativetrace_structlog`` without
it raises ``ModuleNotFoundError`` at the first `import structlog` inside that module. A project
whose source imports ``narrativetrace_structlog`` but whose environment cannot resolve ``structlog``
itself is standing in exactly that gap."""

from __future__ import annotations

import re

from narrativetrace.doctor.doc_urls import DOC
from narrativetrace.doctor.finding import failed, passed
from narrativetrace.doctor.types import DoctorSnapshot, Finding

ID = "trap.llms-before-you-start"
_IMPORTS_STRUCTLOG_BRIDGE = re.compile(r"\bnarrativetrace_structlog\b")
_FIX = (
    "Add structlog explicitly (`uv add structlog`) — on PyPI's published 0.1.1, "
    "narrativetrace-structlog declares it as an optional extra, not a hard dependency, so it is "
    "not pulled in automatically."
)


def _imports_structlog_bridge(snapshot: DoctorSnapshot) -> bool:
    return any(
        path.endswith(".py") and _IMPORTS_STRUCTLOG_BRIDGE.search(content)
        for path, content in snapshot.source_files.items()
    )


def check_llms_before_you_start(snapshot: DoctorSnapshot) -> Finding:
    if not _imports_structlog_bridge(snapshot):
        message = "no source file imports narrativetrace_structlog — nothing to check"
        return passed(ID, message, DOC["sixty_seconds_new_project"])
    if "structlog" in snapshot.installed_packages:
        message = "narrativetrace_structlog is used and structlog resolves in this environment"
        return passed(ID, message, DOC["sixty_seconds_new_project"])
    message = (
        "narrativetrace_structlog is imported but structlog does not resolve in this environment"
    )
    return failed(ID, message, _FIX, DOC["sixty_seconds_new_project"])
