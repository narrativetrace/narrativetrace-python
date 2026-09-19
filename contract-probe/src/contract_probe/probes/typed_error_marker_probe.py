# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`probed-typed-error-marker`: when a field's own getter raises while being rendered, that part
renders `<error: TypeName>` -- the exception's own message is excluded --
documentation/privacy-and-redaction.md `#what-the-deny-list-catches-and-what-outranks-it`.

The fixture is an enum member with a raising `__str__`, not a fieldless plain class: since
0.1.3 a fieldless value never speaks for itself, so its own `__str__` is never called and the
typed error marker would never appear -- it belongs only to a conversion rendering DOES run, and
an enum member's own string conversion is one of those (see
`packages/narrativetrace/tests/test_rendering.py`'s
`test_a_raising_str_on_a_trusted_conversion_renders_the_typed_error_marker`, the unit test this
probe fixture mirrors).
"""

from __future__ import annotations

from enum import Enum

from narrativetrace import ValueRenderer


class _RaisingMember(Enum):
    ONE = "one"

    def __str__(self) -> str:
        raise ValueError("contract-probe: this message must never reach output")


def observe() -> str:
    return ValueRenderer().render(_RaisingMember.ONE)
