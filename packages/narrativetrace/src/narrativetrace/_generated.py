# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Exclusion list 1 -- what is structurally never a business boundary in Python.

Built in and not configurable: no setting re-enables a member, and nothing here is reported.
Membership is a structural property of the object, never a vendor's module name:

* a target whose type is defined by the interpreter itself (``type(target).__module__ ==
  "builtins"``: ``list``, ``dict``, ``str``, ...) -- C-accelerated, no business logic to narrate;
* a ``functools.partial`` / ``functools.partialmethod`` object, as a target or as a member -- a
  library-built forwarder whose only behaviour is the callable it wraps;
* a member the C runtime supplies (builtin functions and bound builtin methods, method wrappers,
  slot wrappers, method descriptors) -- ``types.BuiltinFunctionType`` and its siblings;
* a member whose ``__name__`` is not an identifier (``<lambda>``, ``<genexpr>``): a name no
  ``def`` statement can produce, only the compiler;
* a ``_private`` / ``__dunder__`` member -- machinery the runtime calls on its own behalf.

**@llmNote** ``functools.lru_cache`` wrappers and ``functools.wraps``-decorated functions are
deliberately NOT members: ``wraps`` makes the wrapper indistinguishable from the function it
wraps, and a cached business method is still a boundary the reader wants to see.
"""

from __future__ import annotations

import functools
import types

GENERATED_MEMBERS: tuple[tuple[str, str], ...] = (
    (
        "builtins.*",
        "The target's type is defined by the interpreter itself (`list`, `dict`, `str`)",
    ),
    (
        "functools.partial",
        "A `functools.partial` / `partialmethod` object, as a target or as a member",
    ),
    (
        "types.BuiltinFunctionType",
        "A member the C runtime supplies: builtin functions, bound builtin methods, method "
        "wrappers, slot wrappers, method descriptors",
    ),
    ("<lambda>", "A member whose `__name__` is not an identifier (`<lambda>`, `<genexpr>`)"),
    ("_name", "A `_private` or `__dunder__` member: machinery the runtime calls for itself"),
)
"""List 1 as the configuration guide publishes it: (what is never traced, its structural
property). A test holds the guide's table to this tuple."""

_C_RUNTIME_CALLABLES: tuple[type, ...] = (
    types.BuiltinFunctionType,
    types.MethodWrapperType,
    types.WrapperDescriptorType,
    types.MethodDescriptorType,
)
_FUNCTOOLS_FORWARDERS: tuple[type, ...] = (functools.partial, functools.partialmethod)


def is_generated_target(target: object) -> bool:
    """True when ``target`` itself is never a business boundary (see the module docstring)."""
    return type(target).__module__ == "builtins" or isinstance(target, _FUNCTOOLS_FORWARDERS)


def is_generated_member(name: str, member: object) -> bool:
    """True when member ``name`` (already fetched as ``member``) is never a business boundary."""
    if name.startswith("_"):
        return True
    if isinstance(member, _C_RUNTIME_CALLABLES + _FUNCTOOLS_FORWARDERS):
        return True
    return not getattr(member, "__name__", "x").isidentifier()
