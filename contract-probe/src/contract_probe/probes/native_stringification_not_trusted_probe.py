# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`probed-native-stringification-not-trusted`: a composite type carrying instance state is
walked field by field; its own `__str__`/`__repr__` is never trusted, even when it defines one --
documentation/privacy-and-redaction.md `#what-the-deny-list-catches-and-what-outranks-it`.

The field is deliberately named `password` (the deny-list): before this fix, a hand-written
`__str__` that interpolated a sensitive field reached output completely unmediated, past the
deny-list -- so this probe's oracle is exactly that leak, not a hand-rolled comparison against
the field-walked shape.
"""

from __future__ import annotations

from narrativetrace import ValueRenderer

_SECRET = "hunter2"


class _HandWrittenStr:
    def __init__(self, secret: str) -> None:
        self.password = secret

    def __str__(self) -> str:
        return f"HandWrittenStr(password={self.password})"


def observe() -> str:
    rendered = ValueRenderer().render(_HandWrittenStr(_SECRET))
    return "field-walked-not-str" if _SECRET not in rendered else "str-trusted"
