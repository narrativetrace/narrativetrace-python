# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The minimal use of `narrated` and `not_traced`, run for real -- the block
`documentation/privacy-and-redaction.md` and `documentation/guides/decorators.md` embed right
under their own import lines, so importing either primitive comes with its smallest working use
and the assertion that proves it, in the same place a reader meets the import.

`@narrated` attaches a narration template; `@not_traced` redacts a named parameter. Stacked on one
method (the same pairing `packages/narrativetrace/tests/test_trace_object.py`'s `AuthService`
already exercises), the second shows why stacking order does not matter: the template names
`password` too, and redaction still wins -- `[REDACTED]`, never the literal value, inside the
narration text as well as the argument list (see documentation/privacy-and-redaction.md's
"Redaction wins over a template that names it"). `ProseRenderer` is the renderer that puts both
proofs on the same line: the narration itself (`@narrated`), with the marker where the value
would be (`@not_traced`).
"""

from __future__ import annotations

# snippet:begin main
from narrativetrace import (
    ContextVarNarrativeContext,
    ProseRenderer,
    narrated,
    not_traced,
    trace_object,
)


class AuthService:
    @narrated("login attempt for {username} with {password}")
    @not_traced("password")
    def login(self, username: str, password: str) -> str:
        return f"session-for-{username}"


def run() -> str:
    """Traces one login and renders the result -- `password` never reaches it, in the argument
    list or in the narration template that names it."""
    context = ContextVarNarrativeContext()
    service = trace_object(AuthService(), context)
    service.login("alice", "hunter2")
    return ProseRenderer().render(context.capture_trace())


# snippet:end main

# Imported down here, not at the top of the file: see examples/not_traced_fields.py for why a
# module-level import next to the `# snippet:begin main` marker above would pull an
# artifact-writing detail into the documentation-facing snippet, which has nothing to do with it.
from pathlib import Path  # noqa: E402 -- deliberately not at the top, see comment above


def write_artifact() -> str:
    """Runs :func:`run` and saves its output under ``build/`` for ``scripts/snippet_check.py``
    to embed as documentation's "you imported this — apply it like this" output block (mirrors
    ``examples/not_traced_fields.py``) -- idempotent, safe to call more than once."""
    rendered = run()
    build_dir = Path(__file__).parent / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "import_and_use.txt").write_text(rendered, encoding="utf-8")
    return rendered


if __name__ == "__main__":
    print(run())
