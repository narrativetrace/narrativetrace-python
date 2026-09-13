# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The sanitized-text micro-type every sequence-grammar hook accepts.

``DiagramLabel`` wraps one piece of text guaranteed to have passed through
:mod:`narrativetrace_diagrams.text` -- the one sanitizer both sequence grammars share.

INTENT: "call the sanitizer before this reaches a diagram line" used to be a convention every call
site had to remember on its own -- :mod:`text`'s functions are plain ``str`` transforms that
nothing stopped a caller from skipping. Wrapping the sanitized text in a type makes the convention
structural: a :class:`~narrativetrace_diagrams.sequence_grammar.SequenceGrammar` hook that
declares a ``DiagramLabel`` parameter cannot be called with a raw trace string, sanitized or not,
because nothing outside this module can produce the construction token the dataclass requires.

:meth:`identifier`, :meth:`quoted_identifier`, :meth:`message` and :meth:`alias` are the only
routes from untrusted trace metadata into a label -- each delegates to :mod:`text`'s existing
sanitizer, unchanged. :meth:`with_parameters` and :meth:`aliased_as` compose labels that are
already sanitized, joining their text with literal punctuation that never came from the trace
(``(``, ``, ``, ``" as "``) -- so composition can never reopen the hole the sanitizer closed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from narrativetrace_diagrams import text as _text

_CONSTRUCT = object()


@dataclass(frozen=True, slots=True)
class DiagramLabel:
    """One piece of diagram text guaranteed to have passed through a :mod:`text` sanitizer.

    Constructible only through :meth:`identifier`, :meth:`quoted_identifier`, :meth:`message`,
    :meth:`alias`, or by composing existing labels via :meth:`with_parameters`/:meth:`aliased_as`
    -- direct construction (``DiagramLabel(text)``) raises ``TypeError``, since the private
    construction token is never exported from this module.
    """

    text: str
    _token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _CONSTRUCT:
            raise TypeError(
                "DiagramLabel is constructible only through its factories "
                "(identifier/quoted_identifier/message) or composition "
                "(with_parameters/aliased_as)"
            )

    @staticmethod
    def identifier(raw: str) -> DiagramLabel:
        """Sanitizes one piece of trace metadata (class/method/parameter/exception-type name) for
        interpolation into either diagram grammar. See :func:`text.identifier`."""
        return DiagramLabel(_text.identifier(raw), _CONSTRUCT)

    @staticmethod
    def quoted_identifier(raw: str) -> DiagramLabel:
        """A sanitized identifier, quoted when it contains a character that would otherwise end
        an unquoted token -- the label a participant declaration or an arrow endpoint uses. See
        :func:`text.quote_if_needed`."""
        return DiagramLabel(_text.quote_if_needed(raw), _CONSTRUCT)

    @staticmethod
    def message(value: str) -> DiagramLabel:
        """The message text for a return arrow or a thrown value's carrier text -- folds every
        ISO control character and lone surrogate to a space. See :func:`text.diagram_message`."""
        return DiagramLabel(_text.diagram_message(value), _CONSTRUCT)

    @staticmethod
    def alias(raw: str) -> DiagramLabel:
        """A bare, unquotable Mermaid/PlantUML participant alias -- safe unquoted on a
        ``participant X as Name`` declaration and on every arrow line naming it, unlike
        :meth:`identifier`, which can still carry a space, colon or arrow fragment. See
        :func:`text.alias_token`."""
        return DiagramLabel(_text.alias_token(raw), _CONSTRUCT)

    def with_parameters(self, parameters: list[DiagramLabel]) -> DiagramLabel:
        """This label (a sanitized method name) followed by its already-sanitized parameter
        names, comma-joined and parenthesized: ``method(paramA, paramB)``. The parentheses and
        separator are literal, not trace-derived, so this cannot reintroduce anything the
        sanitizer folded."""
        joined = ", ".join(parameter.text for parameter in parameters)
        return DiagramLabel(f"{self.text}({joined})", _CONSTRUCT)

    def aliased_as(self, display_name: DiagramLabel) -> DiagramLabel:
        """This label (a Mermaid alias) followed by the display name it stands for: ``X as
        Name`` -- the participant declaration line Mermaid's alias mode emits."""
        return DiagramLabel(f"{self.text} as {display_name.text}", _CONSTRUCT)
