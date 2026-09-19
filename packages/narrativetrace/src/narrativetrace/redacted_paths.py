# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Decides whether a template path names something redaction hides.

``RedactedPaths`` (the template-resolution family). ``@narrated("charging
{card.cvv}")`` used to print the cvv in full, because template resolution stringified whatever the
accessor returned, without ever asking whether the member it named was redacted. Naming a path must
never weaken the rules that apply to the value directly — the author who needs the value in a
narrative removes ``@not_traced`` from the member, and that removal is the deliberate, reviewable
decision.

The decision itself is :meth:`~narrativetrace.redaction.RedactionPolicy.is_redacted` — the same
call :mod:`narrativetrace.rendering` makes for a reflectively-introspected field. This module only
walks the dotted path, supplying the two inputs that call needs at each segment: the segment's
name, and whether the member it names is marked ``@not_traced`` on its live owner.

A segment naming no member stops the walk and redacts nothing: a placeholder matching no member is
an authoring typo, and treating it as redacted would hide the unresolved-placeholder warning that
exists to catch it. Nothing can leak either way — a path that names nothing resolves to nothing.

**Rendering reads state, never runs behaviour** applies here too: a segment's existence and its
redaction verdict are both decided without ever invoking whatever it names — an existing
``@property`` decides redaction by NAME alone, exactly like a member with no backing field at all
(:func:`~narrativetrace.rendering.read_backing_field` cannot read either), so ``{user.secret}``
resolves to ``[REDACTED]`` without ``secret`` ever running. Only when the walk must continue past
a segment (a further ``.`` in the path) is that segment's actual STATE read, never its accessor —
and only when it has one to read; a computed property with nothing further to walk into simply
stops the walk, same as a missing member.
"""

from __future__ import annotations

from narrativetrace.markers import is_field_not_traced
from narrativetrace.redaction import RedactionPolicy
from narrativetrace.rendering import STATE_MISSING, read_backing_field


def redacts(root: object, path: str, policy: RedactionPolicy) -> bool:
    """Whether any segment of ``path``, walked from ``root``, names a redacted member.

    Redaction applies at every depth: it is the whole path that is refused, so a redacted segment
    in the middle hides everything named below it too.

    Args:
        root: The object the placeholder's leading key resolved to, possibly ``None``.
        path: The dot-separated member path after that key, e.g. ``"card.cvv"``.
        policy: The redaction policy in force — the same one the value renderer applies.

    Returns:
        ``True`` when the path reaches something redaction hides.
    """
    current = root
    for segment in path.split("."):
        if current is None:
            return False
        owner_type = type(current)
        value = read_backing_field(current, segment)
        if value is STATE_MISSING and not hasattr(owner_type, segment):
            return False  # no member of that name at all -- an authoring typo, not a secret
        if policy.is_redacted(segment, annotated=is_field_not_traced(owner_type, segment)):
            return True
        if value is STATE_MISSING:
            return False  # a computed property with no state to continue the walk into
        current = value
    return False
