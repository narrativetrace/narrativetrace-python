# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier A: the redaction oracle over the shared sensitive-vocabulary corpus, in every emitter
this runtime ships.

``RedactionVocabularyPropertyTest``. ``RedactionPolicy`` answering "yes" is not
protection -- protection is the byte never reaching an output. This drives every row of
``redaction.json`` through the value renderer and every downstream emitter, and asserts the
direction the row declares: a canary behind a sensitive name, or a national-id-shaped value,
appears in no byte of any output; a canary behind a near-miss name stays readable.

The visible half carries the same weight as the hidden half, on purpose: a matcher that redacted
everything would satisfy a suite that only ever asserted absence, and the result is a default
teams switch off -- which leaks every field rather than one.

Absence is asserted across every emitter; presence only across the two value renderers --
downstream emitters legitimately escape and re-encode what they are given, so containment there
would be asserting the escaping rule rather than the redaction rule. Absence has no such
asymmetry: no escaping can make a hidden value reappear.

Name rows render as a one-entry ``dict``, because these names are data rather than compile-time
identifiers -- the corpus carries two spellings of the same Spanish word that differ only in
Unicode normalization form, and no dataclass field can declare both.

Before this module existed, ``redaction.json`` was read and shape-checked by
``test_hostile_corpus.py`` but never actually resolved against the live ``RedactionPolicy`` by
any test in this package -- the corpus was loaded, not exercised.
"""

from __future__ import annotations

import pytest
from emitters import captured_value_tree, every_output, metadata_for
from hostile_corpus import RedactionCase, redactions
from oracles import bounded_size, within_budget

from narrativetrace.redaction import REDACTED_MARKER
from narrativetrace.rendering import ValueRenderer

_VALUE_RENDERER_EMITTERS = ("renderer:value-flat", "renderer:value-structured")


def _redacted_names() -> list[RedactionCase]:
    return [case for case in redactions() if case.is_name and case.expects_redaction]


def _every_output(renderer: ValueRenderer, graph: object) -> dict[str, str]:
    """The two value renderers directly, plus every downstream emitter fed the flat rendering --
    matching Java's ``RedactionVocabularyPropertyTest.everyOutput``."""
    flat = renderer.render(graph)
    outputs = {
        "renderer:value-flat": flat,
        "renderer:value-structured": repr(renderer.render_structured(graph)),
    }
    outputs.update(every_output(captured_value_tree(flat), metadata_for("s")))
    return outputs


class TestCorpusRedactionRows:
    @pytest.mark.parametrize("case", redactions(), ids=str)
    def test_every_corpus_row_goes_the_way_it_declares(self, case: RedactionCase) -> None:
        renderer = ValueRenderer()
        outputs = within_budget(
            f"every output for {case.id}", lambda: _every_output(renderer, case.payload)
        )

        if case.expects_redaction:
            for emitter, output in outputs.items():
                assert case.secret not in output, (
                    f"{case.id} ({case.description}) reached {emitter}"
                )
        else:
            for emitter in _VALUE_RENDERER_EMITTERS:
                assert case.secret in outputs[emitter], (
                    f"{case.id} ({case.description}) must stay readable in {emitter}"
                )
        bounded_size(outputs)

    @pytest.mark.parametrize("case", _redacted_names(), ids=str)
    def test_a_redacted_field_shows_the_marker_rather_than_nothing(
        self, case: RedactionCase
    ) -> None:
        """A redacted field must leave the marker behind, not silence. Silence satisfies
        containment too, and a reader cannot tell "hidden" from "never captured"."""
        rendered = ValueRenderer().render(case.payload)

        assert REDACTED_MARKER in rendered, f"{case.id} must say it hid something"
        assert case.secret not in rendered

    @pytest.mark.parametrize("case", _redacted_names(), ids=str)
    def test_a_sensitive_name_is_still_hidden_several_containers_deep(
        self, case: RedactionCase
    ) -> None:
        """The bug class rather than the instance: every leak found so far lived in a wrapper.
        A sensitive name three containers deep is the same secret."""
        nested = {"outer": [[case.payload]]}
        renderer = ValueRenderer()

        outputs = _every_output(renderer, nested)

        for emitter, output in outputs.items():
            assert case.secret not in output, f"{case.id} reached {emitter} nested"


class TestCorpusShape:
    def test_the_corpus_covers_both_directions_and_both_axes(self) -> None:
        rows = redactions()

        assert len(rows) > 60
        assert any(row.is_name for row in rows)
        assert any(not row.is_name for row in rows)
        assert any(row.expects_redaction for row in rows)
        assert any(not row.expects_redaction for row in rows)
        visible = sum(1 for row in rows if not row.expects_redaction)
        assert visible > 25, "the false-positive half is what keeps the default switched on"
