# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Overall result of a traced scenario, in the two spellings the product needs.

``ScenarioResult``. One fact, two audiences: ``chapter-tree.schema.json`` constrains
``scenario.result`` to ``success``/``error``, while the Markdown caption reads
``**Result:** PASSED``. Carrying both spellings on one enum keeps them from drifting and makes an
out-of-contract value unrepresentable rather than merely untested — the free-form strings that
preceded it wrote ``PASSED`` straight into a JSON artifact the schema rejects.

Never write :attr:`~enum.Enum.name` into an artifact. :attr:`wire_name` is the only spelling the
cross-runtime schema accepts; :attr:`display_name` is for human-facing prose.
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple


class _Spellings(NamedTuple):
    """The pair each member carries as its :attr:`~enum.Enum.value`."""

    wire: str
    display: str


class ScenarioResult(Enum):
    """A scenario's outcome, with its schema-legal and human-facing spellings.

    Members carry both spellings as their value and read them back through properties. Declaring
    ``__init__``/``__new__`` instead would be the obvious spelling and is deliberately avoided:
    :meth:`enum.Enum.__set_name__` calls them *while the class is being created*, which is before
    mutmut's trampoline has its ``_mutmut_orig`` entry — one such method breaks
    ``uv run poe mutate`` for the whole workspace. Pinned by
    ``tests/test_mutation_tooling.py``.
    """

    SUCCESS = _Spellings("success", "PASSED")
    """The scenario completed as intended."""

    ERROR = _Spellings("error", "FAILED")
    """The scenario failed."""

    @property
    def _spellings(self) -> _Spellings:
        """Both spellings, read back off the member's value."""
        spellings: _Spellings = self.value
        return spellings

    @property
    def wire_name(self) -> str:
        """The schema-legal spelling, written into JSON artifacts."""
        return self._spellings.wire

    @property
    def display_name(self) -> str:
        """The human-facing spelling, rendered into Markdown and console output."""
        return self._spellings.display

    @classmethod
    def of(cls, failed: bool) -> ScenarioResult:
        """Maps a test outcome flag to the matching result."""
        return cls.ERROR if failed else cls.SUCCESS

    @classmethod
    def from_text(cls, value: str) -> ScenarioResult:
        """Parses either spelling, case-insensitively.

        Raises:
            TypeError: if ``value`` is not a string.
            ValueError: if it is neither a wire nor a display spelling — the guard that stops an
                out-of-contract value reaching an artifact.
        """
        if not isinstance(value, str):
            raise TypeError("scenario result must be a string")
        normalized = value.strip().lower()
        for candidate in cls:
            if normalized in (candidate.wire_name, candidate.display_name.lower()):
                return candidate
        raise ValueError(
            f"unknown scenario result {value!r}; expected one of success, error, PASSED, FAILED"
        )
