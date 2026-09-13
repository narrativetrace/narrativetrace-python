# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`probed-typed-error-marker`: when a field's own getter raises while being rendered, that part
renders `<error: TypeName>` -- the exception's own message is excluded --
documentation/privacy-and-redaction.md `#what-the-deny-list-catches-and-what-outranks-it`.
"""

from __future__ import annotations

from narrativetrace import ValueRenderer


class _RaisingLeaf:
    __slots__ = ()

    def __str__(self) -> str:
        raise ValueError("contract-probe: this message must never reach output")


def observe() -> str:
    return ValueRenderer().render(_RaisingLeaf())
