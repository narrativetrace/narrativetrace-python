# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Both `@not_traced` field-redaction surfaces, run for real (documentation/guides/decorators.md).

`not_traced_field(...)` marks a dataclass field through its own `field()` metadata.
`__nt_not_traced__` marks any class's fields by name instead — a plain class, a `NamedTuple`, or
an attrs class, anywhere `field(metadata=...)` is not available. Both redact identically: the
value is replaced with `[REDACTED]` before rendering and never reaches a renderer, exporter, or
log.
"""

from __future__ import annotations

# snippet:begin main
from dataclasses import dataclass

from narrativetrace import (
    ContextVarNarrativeContext,
    IndentedTextRenderer,
    not_traced_field,
    trace_object,
)


@dataclass
class Credentials:
    username: str
    secret: str = not_traced_field(default="")


class LegacyCredentials:
    """A plain (non-dataclass) class: `__nt_not_traced__` names the fields to redact."""

    __nt_not_traced__ = ("secret",)

    def __init__(self, username: str, secret: str) -> None:
        self.username = username
        self.secret = secret


class AuthService:
    # Parameter named `account`, not `credentials` -- the latter is itself on the name-based
    # deny-list (see documentation/privacy-and-redaction.md) and would redact the whole argument
    # regardless of which fields inside it are marked `@not_traced`.
    def login(self, account: Credentials | LegacyCredentials) -> str:
        return f"session-for-{account.username}"


def run() -> str:
    """Traces two logins, one per redaction surface, and renders the result."""
    context = ContextVarNarrativeContext()
    service = trace_object(AuthService(), context)
    service.login(Credentials("alice", "hunter2"))
    service.login(LegacyCredentials("bob", "hunter2"))
    return IndentedTextRenderer().render(context.capture_trace())


# snippet:end main

# Imported down here, not at the top of the file: a module-level import next to the
# `# snippet:begin main` marker above, separated only by a comment, is one contiguous block to
# ruff's import sorter -- it would pull this artifact-writing detail into the documentation-facing
# snippet above, which has nothing to do with it. Real statements (the classes and `run()` above)
# between the two keeps them apart.
from pathlib import Path  # noqa: E402 -- deliberately not at the top, see comment above


def write_artifact() -> str:
    """Runs :func:`run` and saves its output under ``build/`` for ``scripts/snippet_check.py``
    to embed as documentation/guides/decorators.md's output block (mirrors
    ``examples/sixty_seconds/tutorial_artifacts.py``) -- idempotent, safe to call more than once."""
    rendered = run()
    build_dir = Path(__file__).parent / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "not_traced_fields.txt").write_text(rendered, encoding="utf-8")
    return rendered


if __name__ == "__main__":
    print(run())
