# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`probed-pytest-artifacts-default`: the pytest plugin writes trace artifacts (Markdown/JSON/
diagram/structural) for each non-empty test with no configuration -- `NARRATIVETRACE_OUTPUT`
defaults to `true` -- documentation/guides/pytest.md `#what-you-get`.

`NARRATIVETRACE_OUTPUT` is deliberately left unset here: that absence IS the claim under test.
"""

from __future__ import annotations

from contract_probe.pytest_fixture_support import run_traced_fixture


def observe() -> str:
    work_dir = run_traced_fixture(env={})
    output_dir = work_dir / "narrative-traces"
    has_artifacts = output_dir.is_dir() and any(output_dir.rglob("*.md"))
    return "true" if has_artifacts else "false"
