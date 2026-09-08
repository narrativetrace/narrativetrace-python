# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Keeps the core package rewritable by mutmut's trampoline.

mutmut wraps every mutated function in a trampoline that reads `_mutmut_orig` out of a dict it
only fills in statements emitted *after* the enclosing class body. A method the module calls
while the class is still being created therefore raises `KeyError: '_mutmut_orig'`, and it does
so during collection — so *no* mutant runs, on any module. That is exactly what a member
`__init__` on a tuple-valued `Enum` did to `render/scenario_result.py`, which left
`uv run poe mutate` dead from 2026-08-30 until 2026-08-31.

`Enum.__set_name__` calls `member.__init__(*args)` (and `__new__`, when the enum defines one)
per member at class-creation time, so an enum carrying data must read it back off `value`
instead. This sweep is the gate: it fails on the *next* enum that reintroduces the hole, rather
than leaving a future agent to rediscover it from a collection error.
"""

from __future__ import annotations

import pkgutil
from enum import Enum
from importlib import import_module

import narrativetrace


def _core_enums() -> list[type[Enum]]:
    """Every `Enum` subclass defined anywhere under the `narrativetrace` core package."""
    found: dict[str, type[Enum]] = {}
    for module_info in pkgutil.walk_packages(narrativetrace.__path__, "narrativetrace."):
        module = import_module(module_info.name)
        for member in vars(module).values():
            if not isinstance(member, type) or not issubclass(member, Enum):
                continue
            if member.__module__ == module_info.name:
                found[f"{member.__module__}.{member.__qualname__}"] = member
    return list(found.values())


def _is_declared_by_the_enum_itself(enum: type[Enum], hook: str) -> bool:
    """True when `hook` is written in the enum's own module, not installed by `enum.EnumType`.

    Every enum class dict carries an `__new__` that `EnumType` puts there; only one whose
    `__module__` is the enum's own is source mutmut would rewrite.
    """
    declared = vars(enum).get(hook)
    return declared is not None and getattr(declared, "__module__", None) == enum.__module__


class TestEnumsStayTrampolineSafe:
    def test_the_sweep_actually_finds_the_core_enums(self) -> None:
        assert "ScenarioResult" in {enum.__name__ for enum in _core_enums()}

    def test_no_enum_runs_its_own_code_while_its_class_is_being_created(self) -> None:
        offenders = {
            f"{enum.__module__}.{enum.__qualname__}.{hook}"
            for enum in _core_enums()
            for hook in ("__init__", "__new__")
            if _is_declared_by_the_enum_itself(enum, hook)
        }
        assert offenders == set()
