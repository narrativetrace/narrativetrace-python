# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The model a ledger row records is always a full model id, never an alias (B-99).

``--model haiku`` is a convenient spelling for the Claude lane, but the promotion matrix groups
rows by the recorded string: an alias splits one model into two groups and made a fresh render of
``ledger/promotion.md`` differ from the committed one. ``resolve_model`` is applied once, where
the runner parses its arguments, so the agent command the lane invokes and the row it writes carry
the same id and cannot drift. ``scripts/promotion_render.py`` applies ``is_full_id`` to every
committed ledger row.
"""

from __future__ import annotations

import re

MODEL_ALIASES = {
    "haiku": "claude-haiku-5-5",
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
}

# ``auto`` is Cursor's own routing id (``--platform cursor --model auto``, see README.md).
_FULL_ID = re.compile(r"\A(?:auto|[a-z][a-z0-9.]*(?:-[a-z0-9.]+)+)\Z")


def is_full_id(model: str) -> bool:
    """True for ``auto`` or a hyphenated slug that carries a digit (``claude-haiku-5-5``,
    ``gemini-3.8-flash-low``); false for an alias (``haiku``) or an empty/odd string."""
    return bool(_FULL_ID.match(model)) and (model == "auto" or any(c.isdigit() for c in model))


def resolve_model(model: str) -> str:
    """The full id for ``model``: an alias is looked up, a full id passes through. Anything else
    raises ``ValueError`` naming the accepted aliases' ids."""
    resolved = MODEL_ALIASES.get(model, model)
    if not is_full_id(resolved):
        accepted = ", ".join(MODEL_ALIASES.values())
        raise ValueError(
            f"unknown model {model!r}; use one of {accepted} (aliases: "
            f"{', '.join(MODEL_ALIASES)}) or another full model id"
        )
    return resolved
