# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`reflectable-structlog-depends-on-structlog`: `narrativetrace-structlog` declares a direct
(non-optional) dependency on `structlog`, not an optional extra --
documentation/guides/installation.md `#installation`.

Reads the installed distribution's own metadata (`Requires-Dist`) -- no code runs, no import of
`structlog` itself is attempted, matching the `reflectable-default` kind: a plain fact already
recorded on the published artifact, read rather than exercised.
"""

from __future__ import annotations

from importlib import metadata


def observe() -> str:
    requirements = metadata.requires("narrativetrace-structlog") or []
    for requirement in requirements:
        name, _, marker = requirement.partition(";")
        if name.strip().lower().split()[0].startswith("structlog") and "extra ==" not in marker:
            return "true"
    return "false"
