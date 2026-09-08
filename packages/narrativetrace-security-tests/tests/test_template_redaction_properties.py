# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier A, target 4: template parsing and rendering.

``TemplateRedactionPropertyTest``. A narration is prose the author wrote, so it can
reach every artifact without ever passing through :class:`~narrativetrace.rendering.ValueRenderer`
-- which is what let "a template naming a redacted path prints it in full" become a leak the
renderer's own tests could not see. The owner's ruling of 2026-08-31 settled the product question:
redaction wins, at every depth of the path.

A security fuzz suite finding (the same defect class every runtime pins, 2026-09-02) found the same
shape one level up: naming the *whole object* rather than a path into it used to skip redaction
entirely, because only the ``{card.cvv}`` path form ever consulted
:func:`narrativetrace.redacted_paths.redacts` -- a bare ``{card}`` placeholder rendered the
object's own ``str()``/``repr()`` unconditionally. The ``wide``/``chain`` corpus fixtures
(``hostile_graphs.template_values``) additionally pin the narrower failure mode inside that same
bug class: a safe rendering that has *truncated a redacted member away* (past the object-field cap
or the recursion-depth cap) carries no redaction marker either, so "no marker" cannot be read as
"nothing hidden" -- only "the value's own text never stood in for the safe rendering" can.

Before this module existed, ``templates.json`` was read and shape-checked by
``test_hostile_corpus.py`` but never actually resolved against a live value map by any test in
this package -- the corpus was loaded, not exercised.
"""

from __future__ import annotations

import pytest
from fuzz_config import fuzz_settings
from hostile_corpus import TemplateCase, templates
from hostile_graphs import template_values
from hypothesis import given
from hypothesis import strategies as st
from oracles import idempotent, sentinel_token, within_budget

from narrativetrace.redaction import REDACTED_MARKER
from narrativetrace.template import resolve


class TestCorpusTemplates:
    @pytest.mark.parametrize("case", templates(), ids=str)
    def test_every_corpus_template_resolves_without_leaking_or_throwing(
        self, case: TemplateCase
    ) -> None:
        sentinel = sentinel_token()
        values = template_values(case.values, sentinel)

        resolved = within_budget(f"template {case.id}", lambda: resolve(case.template, values))

        assert resolved is not None
        assert sentinel not in resolved, f"{case.id} leaked the redacted value"
        if case.expects_redaction:
            assert REDACTED_MARKER in resolved, f"{case.id} fell silent instead of redacting"

    @pytest.mark.parametrize("case", templates(), ids=str)
    def test_every_corpus_template_resolves_identically_twice(self, case: TemplateCase) -> None:
        sentinel = sentinel_token()
        values = template_values(case.values, sentinel)

        idempotent(lambda: resolve(case.template, values))


_REDACTED_PATHS = ("card.cvv", "user.password", "user.secret", "order.card.cvv", "a.b.c.d.secret")
_WHOLE_OBJECT_FIXTURES = ("card", "user", "order", "deep", "unicode", "wide", "chain")
_PROSE = ("", " ", "charging ", " for ", "$", "\n", "[", "]", "%s", "0")
# Bare parameter names the deny-list knows, matching Java's analogous arbitrary exactly: plain
# substring, whole identifier token (`pan`), and the multilingual vocabulary (`senha`,
# `contraseña`, "密码") -- this runtime's default deny-list is multilingual and always on too,
# family standard ported from the Java runtime's `RedactionPolicy` (owner-ordered, closed the
# gap this comment used to flag).
_REDACTED_KEYS = (
    "password",
    "apiToken",
    "cardCvv",
    "secret",
    "sessionId",
    "senha",
    "contraseña",
    "密码",
)
# Names no deny-list knows: what is left is what the bytes themselves say.
_INNOCUOUS_KEYS = ("value", "data", "header", "payload", "item")


def _fixture_for(path: str) -> str:
    root = path.split(".", 1)[0]
    return {"card": "card", "user": "user", "order": "order", "a": "deep"}.get(root, "card")


class TestGeneratedTemplates:
    """The bug class held against generated inputs, not just the fixed corpus list."""

    @fuzz_settings
    @given(st.sampled_from(_REDACTED_PATHS), st.sampled_from(_PROSE))
    def test_a_path_naming_a_redacted_member_always_renders_the_marker(
        self, path: str, surrounding: str
    ) -> None:
        sentinel = sentinel_token()
        values = template_values(_fixture_for(path), sentinel)

        resolved = resolve(f"{surrounding}{{{path}}}{surrounding}", values)

        assert sentinel not in resolved, f"path {path} leaked"
        assert REDACTED_MARKER in resolved, f"path {path} fell silent instead of redacting"

    @fuzz_settings
    @given(st.sampled_from(_REDACTED_KEYS), st.sampled_from(_PROSE))
    def test_a_bare_key_naming_a_secret_always_renders_the_marker(
        self, key: str, surrounding: str
    ) -> None:
        """The other production of the grammar, and the one the property above cannot reach: a
        bare key naming a value directly (2026-09-04 family security fix)."""
        sentinel = sentinel_token()

        resolved = resolve(f"{surrounding}{{{key}}}{surrounding}", {key: sentinel})

        assert sentinel not in resolved, f"key {key} leaked"
        assert REDACTED_MARKER in resolved, f"key {key} fell silent instead of redacting"

    @fuzz_settings
    @given(st.sampled_from(_INNOCUOUS_KEYS))
    def test_a_credential_shaped_scalar_is_refused_whatever_the_key_is_called(
        self, key: str
    ) -> None:
        """The second axis on the same production: the bytes are a credential under any name at
        all (2026-09-04 family security fix)."""
        sentinel = sentinel_token()
        jwt = f"eyJhbGciOiJIUzI1NiJ9.{sentinel}.c2lnbmF0dXJl"

        resolved = resolve("issued {" + key + "}", {key: jwt})

        assert sentinel not in resolved, f"key {key} leaked the token"
        assert REDACTED_MARKER in resolved, f"key {key} fell silent instead of redacting"

    @fuzz_settings
    @given(st.sampled_from(_WHOLE_OBJECT_FIXTURES), st.sampled_from(_PROSE))
    def test_a_whole_object_placeholder_never_leaks_its_redacted_member(
        self, fixture: str, surrounding: str
    ) -> None:
        sentinel = sentinel_token()
        values = template_values(fixture, sentinel)
        placeholder = next(iter(values))

        resolved = resolve(f"{surrounding}{{{placeholder}}}{surrounding}", values)

        assert sentinel not in resolved, f"whole-object fixture {fixture} leaked"

    @fuzz_settings
    @given(st.integers(min_value=1, max_value=50))
    def test_a_redacted_segment_is_refused_at_any_depth_of_path(self, depth: int) -> None:
        sentinel = sentinel_token()
        path = "card" + ".number" * (depth - 1) + ".cvv"

        resolved = resolve("{" + path + "}", template_values("card", sentinel))

        assert sentinel not in resolved

    _BRACE_SOUP_ALPHABET = (
        "{",
        "}",
        ".",
        "card",
        "cvv",
        "number",
        "user",
        "password",
        "secret",
        "a",
        " ",
        "$",
        "\n",
        "[",
        "]",
        "0",
        chr(0x200B),
        chr(0x202E),
    )

    @fuzz_settings
    @given(st.lists(st.sampled_from(_BRACE_SOUP_ALPHABET), max_size=30).map("".join))
    def test_no_generated_template_leaks_the_redacted_component(self, template: str) -> None:
        sentinel = sentinel_token()

        resolved = resolve(template, template_values("card", sentinel))

        assert sentinel not in resolved
