# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Real coverage-guided fuzzing of target 1 (`parse_traceparent`) via atheris.

Only importable where atheris itself is importable — not this repo's own `.devcontainer`
(`aarch64` Linux) and not any macOS host (see `documentation/security-testing.md` for the dated
evidence). **Verified working** 2026-09-09 on a plain `x86_64` Linux CPython 3.12 interpreter
(`python:3.12-bookworm --platform linux/amd64`, matching GitHub Actions' `ubuntu-latest` and this
repo's own GitLab CI image architecture): a 15-second run of exactly this file drove coverage
from 3 to 28 edges over 70,571 executions, confirming the harness below both imports and actually
fuzzes, not merely that atheris installs. `scripts/fuzz_report.py` (invoked by `poe fuzz`) runs
this as a subprocess only when `atheris` is importable; everywhere else `poe fuzz` runs only the
Hypothesis fallback this package's `fuzz_config.py` documents.

Target 2 (`ValueRenderer` over hostile object graphs) has no atheris harness yet — its input is
an object graph, not a byte string, so a byte-to-graph decoder is a separate, non-trivial piece of
work; the Hypothesis sweep remains its only Tier B coverage today.
"""

from __future__ import annotations

import sys

import atheris

with atheris.instrument_imports():
    from narrativetrace_asgi import parse_traceparent


def fuzz_one_input(data: bytes) -> None:
    """One atheris/libFuzzer trial: decode `data` as text and feed it to the parser.

    Mirrors the oracle `test_traceparent_properties.py` already asserts under Hypothesis: parsing
    a hostile header never raises. A byte sequence that is not valid UTF-8 is itself part of the
    input space this oracle covers (`errors="replace"`), not a reason to skip the trial.
    """
    header = data.decode("utf-8", errors="replace")
    parse_traceparent(header)


def main(argv: list[str]) -> None:
    atheris.Setup(argv, fuzz_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main(sys.argv)
