# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The restated deny-list and the credential shapes — the DATA half of the name and shape rules.

The superset assertion against the runtime's own ``RedactionPolicy`` lives in
``narrativetrace-security-tests``, the one package that may see both layers. What is tested here is
this data's own reach: canonicalisation, all three halves of the ADJACENCY bug class the keyed-
assignment scan lives in, and that a near-miss name is not a secret.
"""

from __future__ import annotations

import pytest

from narrativetrace_tooling.feedback.rules import NAMED_SECRET, VALUE_SHAPE
from narrativetrace_tooling.feedback.vocabulary import (
    canonical,
    contains_a_secret_shape,
    names_a_secret,
)


class TestCanonical:
    @pytest.mark.parametrize(
        "spelling",
        ["contrase\u00f1a", "CONTRASE\u00d1A", "contrasen\u0303a", "Contrasena"],
        ids=["accented", "upper", "decomposed", "plain"],
    )
    def test_every_spelling_of_one_word_folds_to_one_string(self, spelling: str) -> None:
        """The decomposed spelling (``n`` + U+0303) is what a Mac filesystem hands back, and the
        accented one is what a Spanish team types; a deny-list that read them as two words would
        cover whichever one it was written with.

        Every spelling is written as an ESCAPE, never as a raw character: the composed and the
        decomposed form render identically, so a list carrying both as literals is one a reader
        cannot check and pytest silently collapses into one case. It did, here, before this
        comment existed."""
        assert canonical(spelling) == "contrasena"

    def test_a_separator_is_not_stripped(self) -> None:
        """Which is why ``api_key`` and ``apikey`` are two terms rather than one: stripping the
        underscore would also fold ``api_keyring`` into the same string."""
        assert canonical("API_KEY") == "api_key"

    def test_a_cjk_word_folds_to_itself(self) -> None:
        assert canonical("密码") == "密码"


class TestNamesASecret:
    @pytest.mark.parametrize(
        "key",
        [
            "password",
            "userPassword",
            "contrase\u00f1a",
            "contrasen\u0303a",
            "密码",
            "NARRATIVETRACE_API_KEY",
            "Authorization",
            "rutCliente",
            "mimaHash",
        ],
    )
    def test_a_deny_listed_term_anywhere_in_the_key_names_a_secret(self, key: str) -> None:
        assert names_a_secret(key)

    @pytest.mark.parametrize("key", ["scenario", "header", "step", "install", "id", "runtime"])
    def test_a_field_name_a_report_legitimately_carries_is_not_a_secret(self, key: str) -> None:
        assert not names_a_secret(key)


class TestContainsASecretShape:
    @pytest.mark.parametrize(
        "value",
        [
            "ghp_0123456789abcdefghij",
            "github_pat_11ABCDEFG0abcdefghij",
            "AKIAIOSFODNN7EXAMPLE",
            "sk-abcdefghijklmnop0123",
            "xoxb-1234-5678-abcdefghij",
            "-----BEGIN RSA PRIVATE KEY-----",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZGEifQ.dBjftJeZ4CVPmB92K27uhbUJ",
            "4111111111111111",
            "12.345.678-5",
            "52998224725",
            "11.222.333/0001-81",
            "X1234567L",
            "1 84 12 76 451 089 46",
            "11010519491231002X",
        ],
    )
    def test_a_credential_or_identity_shape_is_recognised(self, value: str) -> None:
        assert contains_a_secret_shape(value)

    @pytest.mark.parametrize(
        "value",
        [
            "on 2026-09-02 the doctor reported two findings",
            "invoice 987654321 was the one that failed",
            "ai.narrativetrace:narrativetrace-core:0.2.4",
            "trap.redaction-proof",
        ],
    )
    def test_the_numbers_a_legitimate_report_carries_are_not_shapes(self, value: str) -> None:
        assert not contains_a_secret_shape(value)

    def test_no_checksum_is_verified_here_and_that_is_the_design(self) -> None:
        """A CPF whose check digits are wrong: the renderer leaves it VISIBLE, deliberately,
        because blanking a user's data on a guess is the worse mistake there. This gate refuses it
        anyway — an unfilable report costs a sentence, a public identity number does not. Corpus
        row ``value-shape-checksum-failing-lookalike`` pins the asymmetry."""
        assert contains_a_secret_shape("52998224726")


class TestNamedSecretRule:
    @pytest.mark.parametrize(
        "text",
        [
            "Authorization: Bearer eyJpc3MiOiJhZGEifQ",
            "userPassword=hunter2",
            "contrase\u00f1a: ada-2026",
            "contrasen\u0303a: ada-2026",
            "密码=hunter2",
            "NARRATIVETRACE_API_KEY=abcdefghij",
        ],
    )
    def test_refuses_a_deny_listed_name_with_a_value_beside_it(self, text: str) -> None:
        assert NAMED_SECRET.rejects(text)

    def test_the_scan_does_not_eat_the_first_letter_of_the_next_key(self) -> None:
        """Bug class ADJACENCY, half one (Java defect 1, cross-port item 2). Consuming the
        value's first character made the scan resume INSIDE the next key: this paste matched
        ``datasource:``, resumed at ``p``, read the key as ``assword`` and let the credential
        through. Corpus row ``named-secret-yaml-indented``."""
        assert NAMED_SECRET.rejects("spring:\n  datasource:\n    password: hunter2")

    def test_the_scan_is_not_truncated_by_a_combining_mark_inside_the_key(self) -> None:
        """Bug class ADJACENCY, half three — this port's own, found here. Java's
        ``UNICODE_CHARACTER_CLASS`` makes ``\\w`` include the combining-mark categories; Python's
        Unicode ``\\w`` does not. So ``contrasen`` + U+0303, the decomposed spelling a Mac
        filesystem hands back, truncated at the mark and the scan read the key as ``a``. The key
        is defined by its SEPARATORS now, so no character can truncate one. Corpus row
        ``named-secret-spanish-decomposed``."""
        assert NAMED_SECRET.rejects("contrasen\u0303a: ada-2026")

    def test_the_scan_reads_a_quoted_key(self) -> None:
        """Bug class ADJACENCY, half two (Java defect 2, cross-port item 2). A JSON key is
        ``"password": "hunter2"`` and the closing quote sits between the key and the colon — so
        without optional quotes the one attachment every report carries, the doctor's own JSON,
        was the one format the deny-list could not read at all. Corpus row
        ``named-secret-json-quoted``."""
        assert NAMED_SECRET.rejects('{\n  "datasource": {\n    "password": "hunter2"\n  }\n}')

    @pytest.mark.parametrize(
        "text",
        [
            "the authorization header: it never arrived at all",
            "- Login.authenticate(username, password)",
            "scenario: Weekend trip settles with three transfers",
            "did:\n\tran the doctor twice",
        ],
    )
    def test_accepts_a_deny_listed_word_that_is_not_the_key_being_assigned(self, text: str) -> None:
        """Anchored on the key being ASSIGNED, not on the word appearing anywhere: a report that
        says "the authorization header never arrived" is the report we want, and the key there is
        ``header``. A parameter NAME is shape and may stay; only a value beside it may not."""
        assert not NAMED_SECRET.rejects(text)

    def test_a_deny_listed_key_with_nothing_after_the_colon_is_shape_not_a_value(self) -> None:
        assert not NAMED_SECRET.rejects("password:")


class TestValueShapeRule:
    def test_refuses_a_credential_shape_in_the_middle_of_a_sentence(self) -> None:
        assert VALUE_SHAPE.rejects("the token it printed was ghp_0123456789abcdefghij")

    def test_accepts_a_sentence_with_no_shape_in_it(self) -> None:
        assert not VALUE_SHAPE.rejects("the doctor's fix for trap.redaction-proof did not work")
