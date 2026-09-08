# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the name-based RedactionPolicy deny-list."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from narrativetrace.redaction import REDACTED_MARKER, RedactionPolicy
from narrativetrace.rendering import ValueRenderer


class TestDefaultPolicy:
    def test_marker_value(self) -> None:
        assert REDACTED_MARKER == "[REDACTED]"

    @pytest.mark.parametrize(
        "name",
        [
            "password",
            "passwd",
            "secret",
            "token",
            "apikey",
            "api_key",
            "cvv",
            "ssn",
            "authorization",
            "credential",
            "privatekey",
            "private_key",
            "cardnumber",
            "card_number",
            "jwt",
            "cookie",
            "setcookie",
            "set_cookie",
            "sessionid",
            "session_id",
            "accountnumber",
            "account_number",
            "routingnumber",
            "routing_number",
        ],
    )
    def test_default_patterns_redact(self, name: str) -> None:
        assert RedactionPolicy.DEFAULT.should_redact(name)

    def test_default_has_fifty_one_patterns(self) -> None:
        # 26 English + 17 non-English substring patterns + 8 non-English token-boundary
        # patterns (pan/iban were already counted in the English 26).
        assert len(RedactionPolicy.DEFAULT.patterns) == 51

    @pytest.mark.parametrize("name", ["userPassword", "cardCvv", "apiToken", "USER_SSN"])
    def test_case_insensitive_substring_match(self, name: str) -> None:
        assert RedactionPolicy.DEFAULT.should_redact(name)

    @pytest.mark.parametrize("name", ["username", "amount", "orderId", "email"])
    def test_non_sensitive_names_pass(self, name: str) -> None:
        assert not RedactionPolicy.DEFAULT.should_redact(name)

    def test_none_name_is_not_redacted(self) -> None:
        assert not RedactionPolicy.DEFAULT.should_redact(None)


class TestIsRedacted:
    """The one rule `rendering.py`'s field introspection and `redacted_paths.redacts` both
    delegate to, so a member is redacted the same way regardless of which surface names it."""

    def test_annotated_redacts_even_when_the_name_matches_no_pattern(self) -> None:
        assert RedactionPolicy.DEFAULT.is_redacted("clearance", annotated=True)

    def test_deny_listed_name_redacts_even_when_unannotated(self) -> None:
        assert RedactionPolicy.DEFAULT.is_redacted("password", annotated=False)

    def test_neither_annotated_nor_deny_listed_is_not_redacted(self) -> None:
        assert not RedactionPolicy.DEFAULT.is_redacted("username", annotated=False)

    def test_disabled_policy_still_honours_the_annotation(self) -> None:
        assert RedactionPolicy.DISABLED.is_redacted("password", annotated=True)


class TestDisabledAndCustom:
    def test_disabled_redacts_nothing(self) -> None:
        assert not RedactionPolicy.DISABLED.should_redact("password")

    def test_of_patterns_replaces_defaults(self) -> None:
        policy = RedactionPolicy.of_patterns({"custom"})
        assert policy.should_redact("myCustomField")
        assert not policy.should_redact("password")

    def test_of_patterns_is_case_insensitive(self) -> None:
        policy = RedactionPolicy.of_patterns({"SECRET"})
        assert policy.should_redact("client_secret")


class TestPanIbanTokenBoundary:
    """``pan``/``iban`` are the two default patterns short enough that a naive substring test
    would redact ordinary business fields; see the module docstring and adversarial-audit F3."""

    @pytest.mark.parametrize(
        "name",
        ["pan", "PAN", "card_pan", "cardPan", "panNumber", "iban", "IBAN", "account_iban"],
    )
    def test_pan_and_iban_redact_as_whole_tokens(self, name: str) -> None:
        assert RedactionPolicy.DEFAULT.should_redact(name)

    def test_oddly_cased_iban_redacts_by_whole_name_even_though_tokenising_splits_it(
        self,
    ) -> None:
        assert RedactionPolicy.DEFAULT.should_redact("IbAn")

    @pytest.mark.parametrize(
        "name",
        [
            "companyName",
            "expansionRatio",
            "panelId",
            "spanCount",
            "planId",
            "japaneseAddress",
            "company_name",
            "urban_planning",
        ],
    )
    def test_pan_and_iban_do_not_redact_as_substrings(self, name: str) -> None:
        assert not RedactionPolicy.DEFAULT.should_redact(name)


class TestMultilingualVocabulary:
    """The default vocabulary is multilingual and always on -- the family standard, shared by
    every NarrativeTrace runtime (gates the v0.1.0 release). No locale to
    select, nothing to opt into: Spanish, Portuguese, French and Chinese words sit beside the
    English ones."""

    @pytest.mark.parametrize("name", ["contraseña", "tarjeta", "cédula", "rut", "cuit", "dni"])
    def test_default_redacts_spanish_sensitive_names(self, name: str) -> None:
        assert RedactionPolicy.DEFAULT.should_redact(name)

    @pytest.mark.parametrize("name", ["senha", "cpf", "cnpj", "cartão"])
    def test_default_redacts_portuguese_sensitive_names(self, name: str) -> None:
        assert RedactionPolicy.DEFAULT.should_redact(name)

    @pytest.mark.parametrize("name", ["motDePasse", "mot_de_passe", "nir"])
    def test_default_redacts_french_sensitive_names(self, name: str) -> None:
        assert RedactionPolicy.DEFAULT.should_redact(name)

    @pytest.mark.parametrize("name", ["密码", "用户密码", "身份证", "mima", "shenfenzheng"])
    def test_default_redacts_chinese_sensitive_names(self, name: str) -> None:
        # 密码 = mima ("password"); 身份证 = shenfenzheng ("identity card")
        assert RedactionPolicy.DEFAULT.should_redact(name)

    @pytest.mark.parametrize(
        ("accented", "unaccented"),
        [
            ("contraseña", "contrasena"),
            ("CONTRASEÑA", "CONTRASENA"),
            ("cédula", "cedula"),
            ("CartãoCredito", "CartaoCredito"),
        ],
    )
    def test_accented_and_unaccented_spellings_are_matched_alike(
        self, accented: str, unaccented: str
    ) -> None:
        assert RedactionPolicy.DEFAULT.should_redact(accented)
        assert RedactionPolicy.DEFAULT.should_redact(unaccented)

    def test_the_decomposed_spelling_is_the_same_word(self) -> None:
        # n + U+0303 (combining tilde) rather than the precomposed U+00F1.
        assert RedactionPolicy.DEFAULT.should_redact("contraseña")

    @pytest.mark.parametrize(
        "name",
        [
            "rutCliente",
            "cuitEmpresa",
            "dniTitular",
            "senhaUsuario",
            "cpf_cliente",
            "CNPJ",
            "nirAssure",
            "mimaHash",
        ],
    )
    def test_non_english_short_names_match_as_identifier_tokens_in_compound_names(
        self, name: str
    ) -> None:
        assert RedactionPolicy.DEFAULT.should_redact(name)

    @pytest.mark.parametrize(
        "name",
        [
            "truthValue",
            "bruteForceAttempts",
            "scrutinyScore",
            "circuitBreaker",
            "biscuitCount",
            "midnightCutoff",
            "chosenHash",
            "frozenHashes",
            "nirvanaLevel",
            "semiMajorAxis",
        ],
    )
    def test_short_non_english_words_do_not_blank_ordinary_business_fields(self, name: str) -> None:
        assert not RedactionPolicy.DEFAULT.should_redact(name)

    @pytest.mark.parametrize(
        "name",
        [
            "enclaveId",
            "conclaveDate",
            "cartesianProduct",
            "descartesPoint",
            "carteraDigital",
            "clave",
            "clavePrimaria",
            "claveForanea",
            "llavePrimaria",
            "carte",
            "carteGraphique",
            "carteRoutiere",
        ],
    )
    def test_clave_and_carte_stay_visible_bare_and_in_ordinary_compounds(self, name: str) -> None:
        """Narrowed out of the deny-list entirely (family ruling 2026-09-03): a token match only
        ever protected them from *someone else's* compound, never from a codebase's own -- the
        pattern was itself a whole token there too."""
        assert not RedactionPolicy.DEFAULT.should_redact(name)

    @pytest.mark.parametrize(
        "name",
        [
            "claveAcceso",
            "clave_acceso",
            "claveSecreta",
            "clave_secreta",
            "carteBancaire",
            "carte_bancaire",
            "numeroCarte",
            "numero_carte",
        ],
    )
    def test_narrowed_clave_and_carte_compounds_are_redacted(self, name: str) -> None:
        assert RedactionPolicy.DEFAULT.should_redact(name)

    def test_disabled_redacts_no_non_english_name_either(self) -> None:
        assert not RedactionPolicy.DISABLED.should_redact("contraseña")
        assert not RedactionPolicy.DISABLED.should_redact("密码")
        assert not RedactionPolicy.DISABLED.should_redact("claveAcceso")


class TestValueShapeMasking:
    """Value-shape masking is a second axis from the name-based deny-list: a JWT/PAN/
    ``Set-Cookie``/national-id-shaped value is redacted regardless of the field name carrying
    it."""

    _JWT = (
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    )
    _PAN = "4111111111111111"
    _SET_COOKIE = "sessionid=abc123; Path=/; HttpOnly"
    _CPF = "52998224725"

    @pytest.mark.parametrize("value", [_JWT, _PAN, _SET_COOKIE, _CPF])
    def test_default_policy_redacts_secret_shaped_values(self, value: str) -> None:
        assert RedactionPolicy.DEFAULT.should_redact_value(value)

    def test_default_policy_leaves_ordinary_values_alone(self) -> None:
        assert not RedactionPolicy.DEFAULT.should_redact_value("ORD-2026-000123")

    def test_disabled_turns_off_value_shape_masking_too(self) -> None:
        assert not RedactionPolicy.DISABLED.should_redact_value(self._PAN)
        assert not RedactionPolicy.DISABLED.should_redact_value(self._CPF)

    def test_of_patterns_keeps_value_shape_masking_on(self) -> None:
        policy = RedactionPolicy.of_patterns({"custom"})
        assert policy.should_redact_value(self._PAN)
        assert policy.should_redact_value(self._CPF)

    def test_a_national_id_is_hidden_through_the_renderer_under_an_innocent_field_name(
        self,
    ) -> None:
        @dataclass
        class Applicant:
            reference: str
            city: str

        renderer = ValueRenderer()
        flat = renderer.render(Applicant(self._CPF, "Recife"))
        structured = repr(renderer.render_structured(Applicant(self._CPF, "Recife")))

        assert self._CPF not in flat
        assert REDACTED_MARKER in flat
        assert self._CPF not in structured
        assert REDACTED_MARKER in structured
        assert "Recife" in flat, "an ordinary field beside it stays readable"
