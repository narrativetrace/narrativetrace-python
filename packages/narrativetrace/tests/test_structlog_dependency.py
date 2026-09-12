# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`narrativetrace-structlog` must hard-depend on `structlog`, not offer it as an opt-in extra.

Found walking this runtime as a fresh agent would (documentation/llms.txt "look further"): the
package's whole purpose is `from narrativetrace_structlog import narrative_context_processor`
fed into `structlog.configure(...)` (see documentation/guides/logging.md) -- but the guide's own
example does `import structlog` first, and `installation.md`/`llms.txt` both tell an agent to
install this integration with a plain `uv add narrativetrace-structlog`. Until this was fixed,
that command installed the processor without `structlog` itself (an opt-in `[project.
optional-dependencies]` extra nothing in the docs ever names), so the guide's own first line
raised `ModuleNotFoundError` on a fresh install -- the same class of defect the TypeScript arm hit
with `vitest` (a peer/optional dependency the integration package should simply supply).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import structlog
from narrativetrace_structlog import narrative_context_processor


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


REPO_ROOT = _repo_root()
STRUCTLOG_PYPROJECT = REPO_ROOT / "packages" / "narrativetrace-structlog" / "pyproject.toml"


def test_structlog_is_a_hard_dependency_not_an_optional_extra() -> None:
    project = tomllib.loads(STRUCTLOG_PYPROJECT.read_text(encoding="utf-8"))["project"]
    dependencies = " ".join(project["dependencies"])
    assert "structlog" in dependencies, (
        "narrativetrace-structlog must depend on structlog directly -- "
        "installation.md and llms.txt both document a plain 'uv add narrativetrace-structlog'"
    )
    assert "structlog" not in project.get("optional-dependencies", {}), (
        "structlog must not be an opt-in extra: the package's only purpose is the structlog "
        "integration, and the guide's own first line imports structlog unconditionally"
    )


def test_the_processor_itself_imports_cleanly_with_structlog_installed() -> None:
    """Proof, not just configuration intent: the guide's own example actually runs."""
    structlog.configure(
        processors=[narrative_context_processor, structlog.processors.JSONRenderer()]
    )
