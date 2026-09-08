# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders canonical entries as a translated trace: re-derivation, never substitution.

``TraceTranslationView``. INTENT: every line is rebuilt from structural fields
(``code.namespace``, ``code.function``, parameter *names*) plus verbatim values — the pre-rendered
``message``/``nt.returnValue``/``exception.message`` fields are never parsed, so no value token is
ever altered by translation (plan safety property 1). Glossed identifiers keep the original
identifier alongside them, so a reader can always map a translated line straight back to code.

``render_entry`` is the atomic unit: the same call renders one line whether it came from a
completed :class:`~narrativetrace.tree.TraceTree`
(:func:`~narrativetrace.tree_canonical.entries_from_tree`, batch — one file per trace) or a live
pipeline stream (:class:`~narrativetrace_glossary.translation_subscriber.TranslationSubscriber`,
one locale as it happens). A property test pins that batch :meth:`render` is byte-identical to the
concatenation of per-entry calls plus the gaps footer, so the two paths can never drift apart.

**Redaction passes through untouched.** A redacted parameter's ``value`` already reads
``"[REDACTED]"`` by the time it reaches this view (capture-time redaction, upstream in
:mod:`narrativetrace.redaction`) — this module only ever glosses parameter *names*, never values,
so it neither re-checks nor could un-redact anything.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from narrativetrace.canonical import CanonicalEntry
from narrativetrace_glossary.context_resolver import UNASSIGNED_CONTEXT, resolve_context
from narrativetrace_glossary.models import Glossary
from narrativetrace_glossary.normalizer import (
    exception_candidate,
    normalize_phrase,
    parameter_candidate,
)
from narrativetrace_glossary.scaffolding import ScaffoldingBundle
from narrativetrace_glossary.translator import GlossaryTranslator

_ENTER = "method_enter"
_EXIT = "method_exit"
_FAILURE = "failure"
_INCOMPLETE = "incomplete"
_INDENT_UNIT = "  "


@dataclass(slots=True)
class RenderState:
    """Per-render mutable state: one instance belongs to one trace's whole render sequence.

    Not thread-safe by design — a single owner (a batch loop, or a live subscriber's one trace)
    drives every call, which is exactly what lets the two render incrementally the same way.
    """

    locale: str
    scaffolding: ScaffoldingBundle
    depths: dict[str, int] = field(default_factory=dict)
    contexts: dict[str, str] = field(default_factory=dict)
    gaps: set[str] = field(default_factory=set)


class TraceTranslationView:
    """Renders canonical entries into one locale: glossary terms glossed, values untouched."""

    def __init__(
        self, glossary: Glossary, namespace_of: Callable[[str], str | None] | None = None
    ) -> None:
        """Args:
        glossary: supplies both the bounded contexts (for context resolution) and the term
            translations.
        namespace_of: fallback module-path resolver for entries captured before schema 1.2
            (``nt.package`` absent). Defaults to "never resolves anything" — ``nt.package`` is
            present on every entry this runtime captures today.
        """
        self._glossary = glossary
        self._namespace_of = (
            namespace_of if namespace_of is not None else (lambda _class_name: None)
        )
        self._translator = GlossaryTranslator(glossary)
        self._single_context = (
            next(iter(glossary.contexts)) if len(glossary.contexts) == 1 else None
        )

    def new_render_state(self, locale: str) -> RenderState:
        """Starts a fresh render sequence for ``locale``."""
        if not locale.strip():
            raise ValueError("locale must not be blank")
        return RenderState(locale, ScaffoldingBundle.for_locale(locale))

    def render(self, entries: Sequence[CanonicalEntry], locale: str) -> str:
        """Batch-renders a whole trace's entries plus its gaps footer."""
        state = self.new_render_state(locale)
        text = "".join(self.render_entry(entry, state) for entry in entries)
        footer = self.render_gaps_footer(state)
        return text + footer if footer else text

    def render_entry(self, entry: CanonicalEntry, state: RenderState) -> str:
        """Renders one canonical entry's line(s) — the atomic unit a live subscriber emits.

        Returns the empty string for anything other than a method enter/exit (a concurrency
        marker — fork/join/async-dispatch — carries no span identity to render against yet), so
        this is total over every entry a live event stream can produce.
        """
        if entry.nt_event_type == _ENTER:
            return self._render_enter(entry, state)
        if entry.nt_event_type == _EXIT:
            return self._render_exit(entry, state)
        return ""

    def render_gaps_footer(self, state: RenderState) -> str:
        """Renders the "glossary gaps" footer: every phrase this render could not translate.

        Empty when nothing is missing, so a caller can append it unconditionally. Sorted, so the
        footer is deterministic regardless of the order phrases were encountered in.
        """
        if not state.gaps:
            return ""
        body = "".join(f"- {gap}\n" for gap in sorted(state.gaps))
        return f"\n---\n{state.scaffolding.gaps_heading}:\n{body}"

    # -- enter ---------------------------------------------------------------#
    def _render_enter(self, entry: CanonicalEntry, state: RenderState) -> str:
        span_id = entry.span_id or ""
        depth = state.depths.get(entry.parent_span_id or "", -1) + 1
        state.depths[span_id] = depth
        context = self._context_of(entry.nt_package, entry.code_namespace)
        state.contexts[span_id] = context
        indent = _INDENT_UNIT * depth
        header = self._header(entry, context, state)
        parameters = self._render_parameters(entry, context, state)
        line = f"{indent}{header}{parameters}\n"
        narration = self._render_narration(entry, context, state, indent)
        return line + narration if narration else line

    def _header(self, entry: CanonicalEntry, context: str, state: RenderState) -> str:
        original = entry.code_function or ""
        function = self._gloss_function(original, context, state)
        namespace = entry.code_namespace or ""
        return f"{namespace}.{function} ({original})" if namespace else f"{function} ({original})"

    def _render_parameters(self, entry: CanonicalEntry, context: str, state: RenderState) -> str:
        if not entry.nt_parameters:
            return ""
        rendered = ", ".join(
            f"{self._gloss_parameter(parameter.name, context, state)}: {parameter.value}"
            for parameter in entry.nt_parameters
        )
        return f" ({rendered})"

    def _render_narration(
        self, entry: CanonicalEntry, context: str, state: RenderState, indent: str
    ) -> str:
        template = entry.nt_narration_template
        if not template:
            return ""
        variant = self._translator.template_variant(template, context, state.locale)
        if variant is None:
            state.gaps.add(template)
            return ""
        filled = variant
        for parameter in entry.nt_parameters or ():
            filled = filled.replace("{" + parameter.name + "}", parameter.value)
        return f"{indent}{_INDENT_UNIT}// {filled}\n"

    # -- exit ------------------------------------------------------------------#
    def _render_exit(self, entry: CanonicalEntry, state: RenderState) -> str:
        span_id = entry.span_id or ""
        indent = _INDENT_UNIT * state.depths.get(span_id, 0)
        context = state.contexts.get(span_id, UNASSIGNED_CONTEXT)
        return f"{indent}{self._exit_body(entry, context, state)}\n"

    def _exit_body(self, entry: CanonicalEntry, context: str, state: RenderState) -> str:
        if entry.nt_outcome == _FAILURE:
            return self._exit_failure(entry, context, state)
        if entry.nt_outcome == _INCOMPLETE:
            return f".. {state.scaffolding.incomplete}"
        if entry.nt_return_value is not None:
            return f"-> {state.scaffolding.returns} {entry.nt_return_value}"
        return f"-> {state.scaffolding.returns}"

    def _exit_failure(self, entry: CanonicalEntry, context: str, state: RenderState) -> str:
        exception_type = entry.exception_type or ""
        phrase = self._exception_phrase(exception_type, context, state)
        return f"!! {phrase} [{exception_type}]: {entry.exception_message}"

    def _exception_phrase(self, exception_type: str, context: str, state: RenderState) -> str:
        try:
            candidate = exception_candidate(exception_type) if exception_type else None
        except ValueError:
            candidate = None
        if candidate is None:
            return exception_type
        translated = self._translator.translate(candidate.phrase, context, state.locale)
        if not translated.complete:
            state.gaps.add(candidate.phrase)
        return translated.text

    # -- shared ------------------------------------------------------------- #
    def _gloss_function(self, original: str, context: str, state: RenderState) -> str:
        """Glosses a method/function name — the whole phrase, no role-suffix stripping.

        Matches how :func:`~narrativetrace_glossary.normalizer.method_candidates` harvests a
        method name's *verb-phrase* candidate: the identifier normalizes as one unit.
        """
        if not original:
            return original
        try:
            phrase = normalize_phrase(original)
        except ValueError:
            return original
        return self._translate_and_track(phrase, context, state)

    def _gloss_parameter(self, name: str, context: str, state: RenderState) -> str:
        """Glosses a parameter name: strips a trailing role token, ``customerId`` -> ``customer``.

        Matches how :func:`~narrativetrace_glossary.normalizer.parameter_candidate` harvests
        parameter names — a role-suffixed identifier and its curated glossary term must normalize
        the same way, or a translation a human already added would silently never match.
        """
        if not name:
            return name
        try:
            candidate = parameter_candidate(name)
        except ValueError:
            return name
        if candidate is None:  # nothing left after stripping the role token — no concept to gloss
            return name
        return self._translate_and_track(candidate.phrase, context, state)

    def _translate_and_track(self, phrase: str, context: str, state: RenderState) -> str:
        translated = self._translator.translate(phrase, context, state.locale)
        if not translated.complete:
            state.gaps.add(phrase)
        return translated.text

    def _context_of(self, nt_package: str | None, code_namespace: str | None) -> str:
        if self._single_context is not None:
            return self._single_context
        module_path = (
            nt_package if nt_package is not None else self._namespace_of(code_namespace or "")
        )
        if module_path is None:
            return UNASSIGNED_CONTEXT
        return resolve_context(self._glossary, module_path)
