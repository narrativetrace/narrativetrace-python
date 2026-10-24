# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The one reading of an exception's message every emitter shares (B-174).

``Threw`` holds the live exception, unlike ``Returned``, which
holds text the value renderer already rendered, so a message never passed the redaction policy:
``ValueError("bad token: eyJ...")`` reached every output in full while the identical string as a
parameter answered ``[REDACTED]``. Every renderer, exporter and listener reads the message here.

**@llmNote** Only the value-shape axis applies: a JWT, a Luhn-valid card number or a
``Set-Cookie`` string inside a message is never legitimate. The name deny-list has nothing to match
on, and blanking messages by keyword would destroy the diagnostic value the message exists for.
Length is deliberately not capped.

**@sideEffects** ``str(exc)`` is application code run once per emitter; a rogue ``__str__`` that
raises degrades to ``<error>`` instead of failing the emitter.
"""

from __future__ import annotations

from narrativetrace.escape import control_sanitize
from narrativetrace.redaction import REDACTED_MARKER, RedactionPolicy

UNREADABLE = "<error>"


def of(exception: BaseException | None) -> str | None:
    """The message an emitter may print: replaced whole by the redaction marker when its bytes are
    a credential, control-escaped always; ``None`` for no exception, ``<error>`` when unreadable."""
    if exception is None:
        return None
    try:
        raw = str(exception)
    except Exception:
        return UNREADABLE
    if RedactionPolicy.DEFAULT.should_redact_value(raw):
        return REDACTED_MARKER
    return control_sanitize(raw)


def text(exception: BaseException | None) -> str:
    """:func:`of` where text rather than ``None`` is needed: ``null`` for no exception."""
    message = of(exception)
    return "null" if message is None else message
