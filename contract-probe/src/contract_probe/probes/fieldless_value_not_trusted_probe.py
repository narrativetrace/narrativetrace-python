# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`probed-fieldless-value-not-trusted`: a value carrying no state reflection can read is not
thereby trusted to describe itself -- it renders as its type name --
documentation/privacy-and-redaction.md `#what-the-deny-list-catches-and-what-outranks-it`.

The fixture is a `ctypes.Structure` subclass: its fields live in C-level descriptors, so `vars()`
is empty while its own `__repr__` prints every one of them. Before this, emptiness was read as
"a stateless leaf", the one shape whose own string conversion rendering may call, and the field
named for the deny-list reached output through it. The oracle is exactly that leak.
"""

from __future__ import annotations

import ctypes

from narrativetrace import ValueRenderer

_SECRET = "hunter2"


class _CStructPassword(ctypes.Structure):
    _fields_ = (("password", ctypes.c_char_p),)

    def __repr__(self) -> str:
        return f"CStructPassword(password={self.password.decode()})"


def observe() -> str:
    rendered = ValueRenderer().render(_CStructPassword(_SECRET.encode()))
    return "type-name-not-repr" if _SECRET not in rendered else "repr-trusted"
