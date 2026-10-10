# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``config.approval-mode`` — committed ``.approved.nt`` baselines, with approval mode off.

INTENT: a baseline is the durable form of what a flow is supposed to do, and it only guards
anything while a run compares against it. With approval mode off the tests pass whatever the
structure does, so a committed baseline reads as protection the project does not have. Mirrors
Java's ``ApprovalModeCheck`` on this runtime's own switch.

**@llmNote** "On" is read where this runtime reads it: ``NARRATIVETRACE_APPROVAL`` in the
environment, ``approval`` in the resolved ``[tool.narrativetrace]``/``narrativetrace.toml`` table,
or the variable set in the project's LIVE code and configuration — in a ``.py`` file only as a
string constant naming exactly that variable, bound to a truthy constant (``os.environ[...] = ``,
``setdefault``/``setenv``/``putenv``, a dict literal), so a comment, a docstring or a list holding
both strings is not the switch; in ``.toml``/``.ini``/``.cfg`` only on a non-comment line, as
``NAME = value``. The NAME is case-sensitive, as an environment variable is; the value is read as
the runtime reads it (``1``/``true``/``yes``/``on``, any case). A ``.received.nt`` or
``.incomplete.nt`` alone is not a baseline: it is what a first approval run writes.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from typing import Final

from narrativetrace_tooling.doctor.doc_urls import DOC
from narrativetrace_tooling.doctor.finding import failed, passed
from narrativetrace_tooling.doctor.types import DoctorSnapshot, Finding

ID: Final = "config.approval-mode"

VARIABLE: Final = "NARRATIVETRACE_APPROVAL"

_TRUTHY: Final = frozenset({"1", "true", "yes", "on"})
"""The values the pytest plugin's ``_truthy`` accepts, after ``strip().lower()``."""

_SETTERS: Final = frozenset({"setdefault", "setenv", "putenv"})
"""Calls whose first two arguments are (name, value): ``os.environ.setdefault``,
``monkeypatch.setenv``, ``os.putenv``."""

_ASSIGNED_IN_TEXT: Final = re.compile(
    r"(?<![\w$])NARRATIVETRACE_APPROVAL[\"']?[=:]"
    r"(?:([\"'])(?i:1|true|yes|on)\1|(?i:1|true|yes|on)$)"
)
"""``NAME=value`` once whitespace is removed: the name exactly (case-sensitive, bounded, so
``X_NARRATIVETRACE_APPROVAL`` is not it), then a truthy value in any case that is either quoted —
a string that ends at its quote, as in an inline TOML table — or unquoted and the rest of the line.
The runtime strips only whitespace, so ``true ; comment`` or ``trueish`` is not on."""

_TEXT_CONFIG_SUFFIXES: Final = (".toml", ".ini", ".cfg")

_FIX: Final = (
    "Turn approval mode on: set NARRATIVETRACE_APPROVAL=true for the test run (or approval = true "
    "under [tool.narrativetrace] in pyproject.toml), then run the whole suite: a run whose "
    "structure differs from its baseline fails and writes a .received.nt to review."
)


def check_approval_mode(snapshot: DoctorSnapshot) -> Finding:
    """Fails when an ``.approved.nt`` exists and nothing switches approval mode on."""
    doc = DOC["approval_traces_end_to_end"]
    if not any(path.endswith(".approved.nt") for path in snapshot.approved_dir_files):
        return passed(
            ID, "no .approved.nt baselines — nothing for approval mode to compare yet", doc
        )
    if _switched_on(snapshot):
        message = ".approved.nt baselines exist and approval mode is on — every run compares them"
        return passed(ID, message, doc)
    message = ".approved.nt baselines exist but approval mode is off — nothing compares them"
    return failed(ID, message, _FIX, doc)


def _switched_on(snapshot: DoctorSnapshot) -> bool:
    if _is_true(snapshot.env.get(VARIABLE)) or _is_true(
        snapshot.narrativetrace_config.get("approval")
    ):
        return True
    return any(_sets_the_variable(path, text) for path, text in snapshot.source_files.items())


def _is_true(value: object) -> bool:
    """Truthy as the runtime reads it: a TOML boolean as itself, any other scalar as its text
    (``1`` -> ``"1"``, on; ``1.0`` -> ``"1.0"``, off), stripped and case-folded."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        value = str(value)
    return isinstance(value, str) and value.strip().lower() in _TRUTHY


def _sets_the_variable(path: str, text: str) -> bool:
    if path.endswith(".py"):
        return any(_is_true(value) for value in _python_assignments(text))
    if path.endswith(_TEXT_CONFIG_SUFFIXES):
        return _text_config_sets(text)
    return False


def _text_config_sets(text: str) -> bool:
    """A non-comment line of a ``.toml``/``.ini``/``.cfg`` file assigning the variable."""
    for line in text.splitlines():
        if line.lstrip().startswith(("#", ";")):
            continue
        if _ASSIGNED_IN_TEXT.search("".join(line.split())) is not None:
            return True
    return False


def _python_assignments(source: str) -> Iterator[object]:
    """Every constant a ``.py`` file binds to the variable's exact name; nothing for a file that
    does not parse."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return
    for node in ast.walk(tree):
        yield from _bound_values(node)


def _bound_values(node: ast.AST) -> Iterator[object]:
    if isinstance(node, ast.Assign):
        yield from _subscript_assignments(node)
    elif isinstance(node, ast.Call) and _is_setter(node.func):
        yield from _setter_values(node)
    elif isinstance(node, ast.Dict):
        yield from _dict_values(node.keys, node.values)


def _subscript_assignments(node: ast.Assign) -> Iterator[object]:
    """``os.environ["NARRATIVETRACE_APPROVAL"] = value``."""
    for target in node.targets:
        if isinstance(target, ast.Subscript) and _names_it(target.slice):
            yield _constant(node.value)


def _setter_values(call: ast.Call) -> Iterator[object]:
    """``setdefault``/``setenv``/``putenv`` naming the variable, positionally or by keyword."""
    name, value = _argument(call, 0, "name"), _argument(call, 1, "value")
    if name is not None and value is not None and _names_it(name):
        yield _constant(value)


def _dict_values(keys: list[ast.expr | None], values: list[ast.expr]) -> Iterator[object]:
    for key, value in zip(keys, values, strict=True):
        if key is not None and _names_it(key):
            yield _constant(value)


def _argument(call: ast.Call, position: int, keyword: str) -> ast.expr | None:
    """A call's argument by position, else by keyword (``monkeypatch.setenv(name=..., value=...)``
    — ``setdefault``/``putenv`` take positional ones only)."""
    if len(call.args) > position:
        return call.args[position]
    return next((k.value for k in call.keywords if k.arg == keyword), None)


def _is_setter(func: ast.expr) -> bool:
    return isinstance(func, ast.Attribute) and func.attr in _SETTERS


def _names_it(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value == VARIABLE


def _constant(node: ast.expr) -> object:
    """A constant's value — an f-string with no placeholder is one — or ``None``."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.JoinedStr) and all(isinstance(p, ast.Constant) for p in node.values):
        return "".join(str(p.value) for p in node.values if isinstance(p, ast.Constant))
    return None
