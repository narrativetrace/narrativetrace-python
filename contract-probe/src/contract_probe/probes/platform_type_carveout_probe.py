# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`probed-platform-type-carveout`: a platform-defined type (`pathlib.Path`, `datetime`,
`decimal.Decimal`, `uuid.UUID`) keeps its own `str()`, unwalked, even though it carries instance
state -- documentation/privacy-and-redaction.md `#what-the-deny-list-catches-and-what-outranks-it`.
"""

from __future__ import annotations

import pathlib

from narrativetrace import ValueRenderer


def observe() -> str:
    value = pathlib.PurePosixPath("/etc/passwd")
    rendered = ValueRenderer().render(value)
    return "own-str-used" if rendered == str(value) else "walked"
