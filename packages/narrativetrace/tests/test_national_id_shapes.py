# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for national-identity-number value-shape detection (family standard, ported from the
Java runtime's ``NationalIdShapesTest``)."""

from __future__ import annotations

import pytest

from narrativetrace.national_id_shapes import is_national_id


class TestNationalIdentityNumbersByTheirOwnCheckDigits:
    """Every scheme gets both halves: a real number that must vanish, and a lookalike that fails
    the checksum and must stay visible. Without the second half the matcher could be "any N
    digits" and every test here would still pass."""

    @pytest.mark.parametrize(
        "value",
        [
            "12.345.678-5",  # Chile, RUT, dotted
            "12345678-5",  # Chile, RUT, plain
            "1234567-4",  # Chile, seven-digit body
            "10000013-K",  # Chile, verifier 10 is written K
            "10000004-0",  # Chile, verifier 11 is written 0
            "529.982.247-25",  # Brazil, CPF, formatted
            "52998224725",  # Brazil, CPF, bare
            "11144477735",  # Brazil, CPF, second example
            "75749118606",  # Brazil, CPF whose first check digit comes from remainder 1
            "99603082430",  # Brazil, CPF whose second check digit comes from remainder 0
            "99351819019",  # Brazil, CPF whose second check digit comes from remainder 2
            "11.222.333/0001-81",  # Brazil, CNPJ, formatted
            "11222333000181",  # Brazil, CNPJ, bare
            "12345678Z",  # Spain, DNI
            "12345678-Z",  # Spain, DNI, hyphenated
            "X1234567L",  # Spain, NIE, X prefix
            "Y1234567X",  # Spain, NIE, Y prefix
            "Z1234567R",  # Spain, NIE, Z prefix
            "184127645108946",  # France, NIR
            "1 84 12 76 451 089 46",  # France, NIR, spaced as it is printed
            "175032A12345606",  # France, NIR, Corsica 2A in the department position
            "180022B75123469",  # France, NIR, Corsica 2B in the department position
            "11010519491231002X",  # China, resident id, X check character
            "440301199001010012",  # China, resident id, numeric check character
            "11010521001231003X",  # China, birth year exactly at the upper bound of the range
        ],
    )
    def test_a_national_identity_number_is_masked_whatever_the_field_is_called(
        self, value: str
    ) -> None:
        assert is_national_id(value)

    @pytest.mark.parametrize(
        "value",
        [
            "52998224726",  # CPF with the last check digit wrong
            "11222333000182",  # CNPJ with the last check digit wrong
            "12345678-6",  # RUT with the wrong verifier
            "12345678A",  # DNI with the wrong check letter
            "X1234567A",  # NIE with the wrong check letter
            "184127645108947",  # NIR with the wrong key
            "110105194912310021",  # Chinese id with the wrong check character
            "110105194913320019",  # Chinese id, valid checksum, thirteenth month
            "123456785",  # a nine-digit order number: a RUT without its verifier separator
            "12345678901",  # an eleven-digit reference that is not a CPF
            "987654321",  # an ordinary invoice number
            "2026-09-02",  # a date, which is digits and a separator too
        ],
    )
    def test_a_lookalike_that_fails_its_checksum_stays_visible(self, value: str) -> None:
        assert not is_national_id(value)

    @pytest.mark.parametrize(
        "value",
        [
            "110105189912310007",  # before the earliest plausible birth year
            "110105210101010004",  # after the latest
            "110105199000010019",  # month 00
            "110105199001000007",  # day 00
            "110105199001320000",  # day 32
        ],
    )
    def test_an_eighteen_digit_number_with_an_impossible_birth_date_is_not_a_resident_id(
        self, value: str
    ) -> None:
        """The birth date embedded at positions 7-14 is most of what separates a Chinese resident
        id from any eighteen-digit number: the check character alone lets one in eleven
        through."""
        assert not is_national_id(value)

    @pytest.mark.parametrize("value", ["11111111111", "22222222222", "99999999999"])
    def test_a_repeated_digit_placeholder_is_not_a_cpf(self, value: str) -> None:
        """Every repeated-digit string satisfies both CPF check digits, and none of them is a
        document -- they are what a form writes when it has none. Rejecting them before the
        checksum is the difference between a matcher and a length test."""
        assert not is_national_id(value)


class TestUsSocialSecurityNumbersByStructuralRule:
    """A US SSN carries no check digit -- nine bare digits are arithmetically indistinguishable
    from an order number, an account id, or an unpunctuated phone number, so only the dashed
    ``AAA-GG-SSSS`` form is recognised; the punctuation is the only evidence the writer meant an
    SSN. The SSA's own structural rules (area/group/serial values that have never been issued)
    stand in for the missing checksum, and rejecting them costs nothing real -- they also keep
    ``000-00-0000``, the placeholder that fills test fixtures and redacted forms everywhere,
    visible rather than blanked as noise."""

    @pytest.mark.parametrize(
        "value",
        [
            "123-45-6789",
            "001-01-0001",
            "899-99-9999",
        ],
    )
    def test_a_dashed_ssn_is_masked_whatever_the_field_is_called(self, value: str) -> None:
        assert is_national_id(value)

    @pytest.mark.parametrize(
        "value",
        [
            "123456789",  # bare, no dashes -- indistinguishable from an order number
            "12-345-6789",  # mis-grouped: 2-3-4
            "123-456-789",  # mis-grouped: 3-3-3
            "123-45-678",  # serial one digit short
            "123-45-67890",  # serial one digit long
        ],
    )
    def test_a_wrong_shape_is_not_an_ssn(self, value: str) -> None:
        assert not is_national_id(value)

    @pytest.mark.parametrize(
        "value",
        [
            "000-12-3456",  # area 000, never issued
            "666-12-3456",  # area 666, never issued
            "900-12-3456",  # area 900-999, reserved for ITINs
            "123-00-4567",  # group 00, never issued
            "123-45-0000",  # serial 0000, never issued
            "000-00-0000",  # the placeholder every fixture and redacted form uses
        ],
    )
    def test_a_never_issued_area_group_or_serial_stays_visible(self, value: str) -> None:
        assert not is_national_id(value)
