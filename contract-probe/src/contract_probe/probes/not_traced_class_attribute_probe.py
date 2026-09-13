# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`probed-not-traced-class-attribute`: a class attribute `__nt_not_traced__` redacts the named
fields on any non-dataclass object, unconditionally -- documentation/guides/decorators.md
`#not_traced--redaction`.
"""

from __future__ import annotations

from narrativetrace import ValueRenderer

_SECRET = "top-secret-value"


class _LegacyCredentials:
    """A plain (non-dataclass) class: `__nt_not_traced__` names the fields to redact -- the exact
    shape documentation/guides/decorators.md shows."""

    __nt_not_traced__ = ("secret",)

    def __init__(self, username: str, secret: str) -> None:
        self.username = username
        self.secret = secret


def observe() -> str:
    rendered = ValueRenderer().render(_LegacyCredentials("alice", _SECRET))
    if _SECRET in rendered:
        return "LEAKED"
    return "[REDACTED]" if "[REDACTED]" in rendered else "NO-MARKER"
