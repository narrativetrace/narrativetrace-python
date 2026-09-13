# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier B platform presets: fills ``run.py``'s ``--agent-command`` seam for each of the three
supported CLIs so a trial can be started with just ``--platform`` — never invented for a platform
the seam doesn't name, and always overridable by passing ``--agent-command`` explicitly (the
preset is a default, not a lock-in).
"""

from __future__ import annotations

from typing import Literal

Platform = Literal["claude", "codex", "gemini"]
PLATFORMS: tuple[Platform, ...] = ("claude", "codex", "gemini")

# Codex and Gemini sit on cheaper plans and run under the sporadic policy (never scheduled,
# promotion points only, quota-guarded, Tier A/A2-green precondition). Claude runs on the
# harness's own regular cadence and is exempt from all three.
SPORADIC_PLATFORMS: frozenset[Platform] = frozenset({"codex", "gemini"})


def is_platform(value: str) -> bool:
    return value in PLATFORMS


def is_sporadic_platform(platform: Platform) -> bool:
    return platform in SPORADIC_PLATFORMS


def is_read_only_skill(skill: str) -> bool:
    """``narrativetrace-doctor`` is scoped read-only by design ("diagnosis only, and read-only:
    it never edits, generates, or deletes a file"); every other cataloged skill installs or edits
    files. Used to pick the least-privileged sandbox/approval mode a trial needs."""
    return skill == "narrativetrace-doctor"


def _codex_command(model: str, skill: str) -> str:
    sandbox = "read-only" if is_read_only_skill(skill) else "workspace-write"
    return f'codex exec --sandbox {sandbox} --model {model} "{{prompt}}"'


def _gemini_command(model: str, skill: str) -> str:
    approval_mode = "plan" if is_read_only_skill(skill) else "auto_edit"
    return f'gemini -p "{{prompt}}" --model {model} --approval-mode {approval_mode}'


def preset_agent_command(platform: Platform, model: str, skill: str) -> str:
    """The default ``--agent-command`` template for ``platform``, ``{prompt}``-substituted by
    ``run.py``. Each CLI uses its own subscription login — the harness never passes an API key,
    so no preset ever threads one through."""
    if platform == "claude":
        return f'claude -p "{{prompt}}" --model {model} --allowed-tools Bash'
    if platform == "codex":
        return _codex_command(model, skill)
    return _gemini_command(model, skill)
