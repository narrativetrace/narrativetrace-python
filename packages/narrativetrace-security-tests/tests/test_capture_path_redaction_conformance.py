# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Replays the shared hostile redaction corpus through the REAL capture path -- ``trace_object``,
the entry point an application actually uses -- not through ``ValueRenderer`` directly.

**Why this file exists.** ``redaction.json``'s 92 rows (multilingual name spellings, accented/
decomposed/folded forms, value shapes, four composite ``kind`` shapes added 2026-09-11, and a
false-positive half) were never the problem: every existing consumer of the corpus -- this
package's own :mod:`test_redaction_vocabulary_properties`,
:mod:`test_value_renderer_redaction_properties` -- drives ``ValueRenderer`` directly, on an object
or a dict. That is one layer below where the confirmed defect lived: ``trace_object._build_capture``
deciding parameter redaction from ``@not_traced`` alone, never asking ``RedactionPolicy``, for a
parameter *name*. A corpus replayed one layer below a defect cannot catch it, however many rows it
has. Java proved this is a real guard, not a decoration, by reverting its own capture fix and
watching 28 of 88 rows fail; the equivalent Python experiment (revert, rerun, confirm red, restore)
is recorded in the commit history and in ``documentation`` -- see the module-level assertion below
that pins the count.

**Real capture path, not a shortcut.** Every row is driven through an actual
:func:`~narrativetrace.trace_object.trace_object`-wrapped method call: a name row traces a method
whose declared parameter is the row's exact name; a value row traces a method with the innocuous
parameter name ``data``. Assertions run against the captured ``ParameterCapture.rendered_value``
*and* every rendered artifact (Markdown, prose, JSON export, canonical entries, chapter, indented
text) -- asserting on rendered text alone is exactly what let the parameter-name defect ship for a
year undetected.
"""

from __future__ import annotations

import unicodedata

import pytest
from hostile_corpus import RedactionCase, redactions
from hostile_redaction_kinds import build as build_kind_case

from narrativetrace.chapter import export_chapter
from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.decorators import traced
from narrativetrace.export import export, export_document
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.indented import IndentedTextRenderer
from narrativetrace.render.markdown import MarkdownRenderer
from narrativetrace.render.prose import ProseRenderer
from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.signature import ParameterCapture
from narrativetrace.trace_object import trace_object
from narrativetrace.tree_canonical import export_canonical_entries

_METADATA = TraceMetadata("Hostile corpus replay", ScenarioResult.SUCCESS)


def _name_cases() -> list[RedactionCase]:
    return [case for case in redactions() if case.is_name]


def _value_cases() -> list[RedactionCase]:
    return [case for case in redactions() if not case.is_name and not case.is_kind]


def _kind_cases() -> list[RedactionCase]:
    return [case for case in redactions() if case.is_kind]


def _would_be_altered_by_python_identifier_compilation(name: str) -> bool:
    """Whether building a real Python parameter literally named ``name`` (source text compiled
    via ``exec``) would silently test a DIFFERENT string than ``name`` itself.

    CPython's tokenizer NFKC-normalises every identifier it compiles (PEP 3131) before the
    redaction check downstream ever sees it. A name that is not already NFKC-stable -- a
    decomposed accent (``n`` + U+0303 combining tilde rather than precomposed ``ñ``) -- would
    silently fold to its composed spelling at compile time, passing the row for a different
    reason than the row claims to test. ``str.isidentifier()`` is checked too, defensively, even
    though every corpus name currently satisfies it (see the verification test below).
    """
    return not name.isidentifier() or unicodedata.normalize("NFKC", name) != name


class TestNfkcNormalizationIsVerifiedNotAssumed:
    """Verified empirically against the actual corpus, not assumed: exactly one row is a
    decomposed spelling CPython's tokenizer would silently re-spell if compiled as a literal
    identifier. This pins the exact affected set so a corpus update that adds, removes, or fixes
    such a row is caught here rather than silently changing what ``test_name_case`` exercises for
    it (see ``_build_named_param_service``, which routes exactly this set through
    ``@traced(...)`` instead of a real declared parameter)."""

    def test_every_corpus_name_is_a_valid_python_identifier(self) -> None:
        non_identifiers = [
            case.id for case in _name_cases() if not (case.name or "").isidentifier()
        ]
        assert non_identifiers == [], (
            f"corpus names that are not valid Python identifiers: {non_identifiers}"
        )

    def test_exactly_the_decomposed_spelling_would_be_altered_by_compilation(self) -> None:
        affected = [
            case.id
            for case in _name_cases()
            if _would_be_altered_by_python_identifier_compilation(case.name or "")
        ]
        assert affected == ["es-contrasena-decomposed"]


def _build_named_param_service(param_name: str) -> object:
    """An instance whose ``method`` takes exactly one parameter (besides ``self``) named
    ``param_name``, through the REAL capture path.

    Prefers a genuine declared parameter -- built via ``exec``, the only way to get a
    data-driven Python identifier -- because that is the ``sig.parameters`` branch of
    :func:`~narrativetrace.trace_object._redacted_params` almost every real traced method
    exercises. Falls back to ``@traced(...)``'s explicit-name mechanism -- the *other* real
    branch of the same function (``meta.traced_names``), which supplies the name as runtime
    string data and never touches the tokenizer -- for the one row a real identifier cannot
    represent faithfully (:class:`TestNfkcNormalizationIsVerifiedNotAssumed` pins that set to
    exactly one row). Every row lands on some real ``trace_object`` code path; none is skipped,
    because ``@traced(...)`` can represent any string at all, with no identifier constraint.
    """
    if not _would_be_altered_by_python_identifier_compilation(param_name):
        namespace: dict[str, object] = {}
        exec(  # nosec B102 - fixed template; param_name is corpus data already checked to be a
            # valid, NFKC-stable Python identifier above, never external/untrusted input
            f"def method(self, {param_name}):\n    return True\n",
            namespace,
        )
        return type("RealParamService", (), {"method": namespace["method"]})()

    def method(self: object, _value: object) -> bool:
        return True

    traced(param_name)(method)
    return type("TracedNameService", (), {"method": method})()


class _ValueParamService:
    """Every value-shape row traces through this one innocuous parameter name -- the entire
    point of the value axis is that it catches a secret-shaped value regardless of what the
    parameter holding it is called."""

    def method(self, data: object) -> bool:
        return True


def _capture_and_render(
    service: object, argument: object
) -> tuple[list[ParameterCapture], list[str]]:
    context = ContextVarNarrativeContext()
    trace_object(service, context).method(argument)  # type: ignore[attr-defined]
    tree = context.capture_trace()
    params = list(tree.roots[0].signature.parameters)
    artifacts = [
        MarkdownRenderer().render_document(tree, _METADATA),
        IndentedTextRenderer().render(tree),
        ProseRenderer().render(tree),
        export(tree),
        export_document(tree, _METADATA),
        export_canonical_entries(tree),
        export_chapter(tree, _METADATA),
    ]
    return params, artifacts


def _assert_no_leak_in_params(where: str, secret: str, params: list[ParameterCapture]) -> None:
    leaked = [p.name for p in params if secret in p.rendered_value]
    assert not leaked, f"{where}: secret reached captured ParameterCapture {leaked}"


def _assert_no_leak_in_artifacts(where: str, secret: str, artifacts: list[str]) -> None:
    leaked = [i for i, artifact in enumerate(artifacts) if secret in artifact]
    assert not leaked, f"{where}: secret reached rendered artifact(s) {leaked}"


def _assert_flagged_redacted(where: str, params: list[ParameterCapture]) -> None:
    """Oracle clause 3: a redacted row's capture must carry ``redacted is True`` -- the clause
    this suite did not check before the 2026-09-10 fix (see module docstring)."""
    unflagged = [p.name for p in params if not p.redacted]
    assert not unflagged, (
        f"{where}: oracle clause 3 -- captured redacted but ParameterCapture.redacted is False "
        f"for {unflagged}"
    )


def _assert_secret_survives(
    where: str, secret: str, params: list[ParameterCapture], artifacts: list[str]
) -> None:
    assert any(secret in p.rendered_value for p in params), (
        f"{where}: secret did not survive in any captured ParameterCapture -- over-redaction"
    )
    assert any(secret in artifact for artifact in artifacts), (
        f"{where}: secret did not survive in any rendered artifact -- over-redaction"
    )


def _assert_not_flagged_redacted(where: str, params: list[ParameterCapture]) -> None:
    """Oracle clause 6: a visible row must carry ``redacted is False`` -- over-flagging is a
    defect too, it makes the ``redacted`` list untrue in the other direction."""
    flagged = [p.name for p in params if p.redacted]
    assert not flagged, (
        f"{where}: oracle clause 6 -- visible row but ParameterCapture.redacted is True for "
        f"{flagged}"
    )


def _assert_case(case: RedactionCase, params: list[ParameterCapture], artifacts: list[str]) -> None:
    """Asserts the full oracle contract (``redaction-oracle-contract-2026-09-10.md``, clauses
    1-6) for one corpus row -- not just leak/visibility (1/2/5), but also the ``redacted`` flag
    itself (3/6). Clause 3 is the one this suite did not check before: a value-shape match
    substituted the marker into every rendered artifact while leaving ``ParameterCapture.redacted``
    False, so a JSON export or any other consumer branching on the flag disagreed with what the
    text already said. Clause 4 (text/structure agreement) is not asserted here because it was
    never the defect -- both were already built from the same marker substitution; only the
    boolean beside them was wrong."""
    secret = case.secret
    where = f"{case.id} ({case.description})"
    if case.expects_redaction:
        _assert_no_leak_in_params(where, secret, params)
        _assert_no_leak_in_artifacts(where, secret, artifacts)
        _assert_flagged_redacted(where, params)
    else:
        _assert_secret_survives(where, secret, params, artifacts)
        _assert_not_flagged_redacted(where, params)


def _assert_kind_case(
    case: RedactionCase, params: list[ParameterCapture], artifacts: list[str]
) -> None:
    """The leak/visibility half of the oracle only (clauses 1/2/5), never the ``redacted`` flag
    (3/6): a ``kind`` composite's canary sits NESTED inside it (a field, a map key), never as the
    traced parameter's own name or its own top-level value shape -- exactly the documented
    boundary on :data:`~narrativetrace.signature.ParameterCapture.redacted` (see
    ``render_for_capture``'s docstring and ``TestRenderForCapture`` in ``test_rendering.py``'s own
    nested-JWT case): nested redaction is real and asserted here, it just does not set the
    parameter-level flag, the same as it would not for a hand-written dataclass with one deep
    sensitive field."""
    secret = case.secret
    where = f"{case.id} ({case.description})"
    if case.expects_redaction:
        _assert_no_leak_in_params(where, secret, params)
        _assert_no_leak_in_artifacts(where, secret, artifacts)
    else:
        _assert_secret_survives(where, secret, params, artifacts)


class TestHostileCorpusNameCasesThroughRealCapturePath:
    """A traced method's declared parameter, named for the row -- the confirmed defect's exact
    surface: ``_build_capture`` deciding redaction from ``@not_traced`` alone."""

    @pytest.mark.parametrize("case", _name_cases(), ids=str)
    def test_name_case(self, case: RedactionCase) -> None:
        assert case.name is not None, f"{case.id}: a name-case row with no name"
        service = _build_named_param_service(case.name)
        params, artifacts = _capture_and_render(service, case.canary)
        _assert_case(case, params, artifacts)


class TestHostileCorpusValueCasesThroughRealCapturePath:
    """A traced method whose parameter is named ``data`` -- innocuous by construction, so only
    the argument's own shape can trigger redaction."""

    @pytest.mark.parametrize("case", _value_cases(), ids=str)
    def test_value_case(self, case: RedactionCase) -> None:
        assert case.value is not None, f"{case.id}: a value-case row with no value"
        params, artifacts = _capture_and_render(_ValueParamService(), case.value)
        _assert_case(case, params, artifacts)


class TestHostileCorpusKindCasesThroughRealCapturePath:
    """A composite the 2026-09-11 family fix governs directly: a curated ``__str__`` overriding
    introspection, the same shape planted as a map key, or a raising ``@narrative_summary`` --
    the exact defects confirmed against published 0.1.1 (read-only investigation the same day).
    Traced through the innocuous ``data`` parameter, same as a value-case row: what matters here
    is the composite's own internal shape, not the parameter name holding it."""

    @pytest.mark.parametrize("case", _kind_cases(), ids=str)
    def test_kind_case(self, case: RedactionCase) -> None:
        assert case.kind is not None, f"{case.id}: a kind-case row with no kind"
        composite = build_kind_case(case.kind, case.canary or "")
        params, artifacts = _capture_and_render(_ValueParamService(), composite)
        _assert_kind_case(case, params, artifacts)


def test_every_corpus_row_ran_and_none_was_skipped() -> None:
    """Counts, reported rather than assumed: the corpus has 92 rows; every one of them is
    parametrized into ``test_name_case``/``test_value_case``/``test_kind_case`` above, and none
    ever calls ``pytest.skip`` -- there is no row this suite silently ran nothing for."""
    total = len(redactions())
    name_count = len(_name_cases())
    value_count = len(_value_cases())
    kind_count = len(_kind_cases())
    assert name_count + value_count + kind_count == total
    assert total == 92, f"expected the shared corpus to hold 92 rows, found {total}"
