# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Finding constructors. Named ``passed``/``failed`` rather than the TypeScript runtime's
``pass``/``fail`` — both are reserved words in Python (``pass`` is a statement)."""

from __future__ import annotations

from narrativetrace.doctor.types import Finding


def passed(check_id: str, message: str, doc_url: str) -> Finding:
    """A passing finding: no fix needed, by construction (see :attr:`Finding.fix`)."""
    return Finding(check_id, "pass", message, "", doc_url)


def failed(check_id: str, message: str, fix: str, doc_url: str) -> Finding:
    """A failing finding: ``fix`` is mandatory — a fail with nothing to do about it is a wording
    bug."""
    return Finding(check_id, "fail", message, fix, doc_url)
