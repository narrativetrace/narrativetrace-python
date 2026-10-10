# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Rewrites an absolute home directory to ``~`` — the one normalisation a draft performs before the
gate reads anything.

Ports Java ``HomePaths``. INTENT: a home path names the account it belongs to, and a problem report
is full of them because that is where people's projects live. Refusing the report would be the wrong
answer to a mistake nobody made on purpose; ``~`` says the same thing about the same file and names
nobody. So this runs FIRST, and :data:`~narrativetrace_tooling.feedback.rules.HOME_PATH` is left as
the backstop for a form this cannot normalise — a UNC share, or a path typed into the body file
after the draft was shown.

**@llmNote** ``/home`` with nothing after it is NOT a home directory, and neither is
``/usr/share/ada``: the account segment has to be present and has to follow one of the three
platform roots. A rewrite that was eager here would turn an ordinary path into ``~`` and make the
report wrong instead of safe.
"""

from __future__ import annotations

import re
from typing import Final

_HOME: Final = re.compile(r"(?:/Users/|/home/)[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+", re.IGNORECASE)
"""The three platform roots followed by one account segment. Whatever follows the account — a
trailing separator and everything after it — survives the rewrite, because it is never matched."""


def to_tilde(text: str) -> str:
    """The text with every home directory replaced by ``~``.

    :raises TypeError: when ``text`` is ``None`` — an absent field is ``""``
    """
    if text is None:
        raise TypeError('the rewriter reads text, never None — an absent field is ""')
    return _HOME.sub("~", text)
