# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Turns a plan or a report into the three things a caller needs: human text, a unified diff for
``--dry-run``, and JSON for whatever wraps the command.

INTENT: the same envelope shape this runtime's doctor already emits — ``{findings…, exit_code}``
there, ``{carrier, actions[], exit_code}`` here, snake_case, two-space indent — so a skill that
gates on one can gate on the other without learning a second format.

**@llmNote** The JSON goes through :func:`json.dumps`, exactly as the doctor's renderer does. The
Java port hand-writes it because the JDK ships no JSON writer; doing that here would be a second
escaping implementation to get wrong.

**@llmNote** Paths are emitted with ``/`` on every platform, so a report is the same text wherever
it ran.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from narrativetrace_tooling.init.action import Action, AdoptPage, FileEdit, Refuse, ReplaceLink
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.report import ExecutionReport, Status
from narrativetrace_tooling.init.unified_diff import render_unified_diff

# Quoted verbatim by documentation/agent-skills.md's "From a registry" section (rule 8, docs as
# tests) — the marker pair around this field is that embed's source, never typed into the page.
# snippet:begin adoptedNote
ADOPTED = "adopted: identical to this carrier's page, so only the provenance line is added"
"""What the plan and the report say about a page that was already ours in everything but a line."""

# snippet:end adoptedNote

_PLANNED = "planned"

_REFUSED = "refused"

_APPLIED = "applied"

_COLUMN = 8


def render_plan(plan: InitPlan, as_json: bool) -> str:
    """The whole of what a caller shows for a plan it has NOT applied: the JSON envelope, or the
    summary followed by the unified diff.

    **@llmNote** Both, not either: the summary alone says nothing about what would change, and the
    diff alone says nothing when there is nothing to change. Every entry point asks THIS rather than
    composing its own pair — a rule that holds on one surface only is not a rule.
    """
    return render_plan_json(plan) if as_json else render_plan_text(plan) + render_diff(plan)


def render_report(report: ExecutionReport, as_json: bool) -> str:
    """The whole of what a caller shows for a plan it has applied."""
    return render_report_json(report) if as_json else render_report_text(report)


def render_plan_text(plan: InitPlan) -> str:
    """One line per action, refusals marked, with the carrier and the counts at the top."""
    _require(plan)
    if plan.is_empty:
        return f"narrativetrace — {plan.carrier}\nnothing to do.\n"
    lines = [
        f"narrativetrace — {plan.carrier}",
        f"{len(plan.actions)} action(s), {len(plan.refusals)} refusal(s)",
        "",
        *(f"{_pad(action.kind)}{_display(action.path)}{_note(action)}" for action in plan.actions),
    ]
    return "".join(f"{line}\n" for line in lines)


def render_report_text(report: ExecutionReport) -> str:
    """One line per action, each saying whether it happened."""
    _require(report)
    refused = sum(1 for result in report.results if result.status is Status.REFUSED)
    lines = [
        f"narrativetrace — {report.carrier}",
        f"{len(report.results) - refused} applied, {refused} refused",
        "",
        *(
            f"{_pad(_status_of(result.status))}{_pad(result.action.kind)}"
            f"{_display(result.action.path)}"
            f"{' — ' + result.detail if result.detail else _note(result.action)}"
            for result in report.results
        ),
    ]
    return "".join(f"{line}\n" for line in lines)


def render_diff(plan: InitPlan) -> str:
    """The full unified diff a dry run shows: one file at a time, in plan order."""
    _require(plan)
    out: list[str] = []
    for action in plan.actions:
        if isinstance(action, FileEdit):
            out.append(render_unified_diff(_display(action.path), action.before, action.after))
        else:
            out.append(f"# {_display(action.path)} — {_describe(action)}\n")
    return "".join(out)


def render_plan_json(plan: InitPlan) -> str:
    """``{"carrier", "actions":[{kind, path, status}], "exit_code"}`` for a plan not yet applied."""
    _require(plan)
    rows = [
        _row(action, _REFUSED if isinstance(action, Refuse) else _PLANNED)
        for action in plan.actions
    ]
    return _envelope(plan.carrier, rows, plan.exit_code)


def render_report_json(report: ExecutionReport) -> str:
    """The same envelope for a plan that has been applied."""
    _require(report)
    rows = [_row(result.action, _status_of(result.status)) for result in report.results]
    return _envelope(report.carrier, rows, report.exit_code)


def _envelope(carrier: str, actions: list[dict[str, str]], exit_code: int) -> str:
    payload: dict[str, Any] = {"carrier": carrier, "actions": actions, "exit_code": exit_code}
    return json.dumps(payload, indent=2)


def _row(action: Action, status: str) -> dict[str, str]:
    return {"kind": action.kind, "path": _display(action.path), "status": status}


def _status_of(status: Status) -> str:
    return _APPLIED if status is Status.APPLIED else _REFUSED


def _describe(action: Action) -> str:
    return f"refused: {action.reason}" if isinstance(action, Refuse) else action.kind


def _note(action: Action) -> str:
    """What a line says after the path: why a refusal refused, which link a replacement replaces,
    or — for an adoption — that nothing of anybody's was overwritten.

    Asked by BOTH the plan's text and the report's, because an adoption a person only sees in a
    preview is an adoption they were never told about.
    """
    if isinstance(action, Refuse):
        return f" — {action.reason}"
    if isinstance(action, ReplaceLink):
        return f" — replaces the symbolic link {_display(action.link)} → {action.target}"
    return f" — {ADOPTED}" if isinstance(action, AdoptPage) else ""


def _display(path: Path) -> str:
    """A path as every platform should read it: its own elements joined with ``/``, so a Windows
    separator never reaches the output and a backslash that is part of a NAME survives."""
    return path.as_posix()


def _pad(word: str) -> str:
    return word + " " if len(word) >= _COLUMN else word.ljust(_COLUMN)


def _require(rendered: object) -> None:
    if rendered is None:
        raise TypeError("there is nothing to render")
