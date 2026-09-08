# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Mechanical rename suggestions: casing-aware token splicing."""

from __future__ import annotations

import pytest
from narrativetrace_glossary import suggest_rename


def test_splices_a_canonical_phrase_into_snake_case() -> None:
    assert (
        suggest_rename("open_account_with_overdraft", "open overdraft account")
        == "open_overdraft_account"
    )


def test_splices_a_canonical_phrase_into_camel_case() -> None:
    assert (
        suggest_rename("openAccountWithOverdraft", "open overdraft account")
        == "openOverdraftAccount"
    )


def test_splices_a_canonical_phrase_into_pascal_case() -> None:
    assert (
        suggest_rename("OpenAccountWithOverdraft", "open overdraft account")
        == "OpenOverdraftAccount"
    )


def test_single_token_canonical_phrase_in_pascal_case() -> None:
    assert suggest_rename("AccountSvc", "account") == "Account"


def test_single_token_canonical_phrase_in_camel_case() -> None:
    assert suggest_rename("accountSvc", "account") == "account"


def test_single_token_identifier_defaults_to_snake_case_style() -> None:
    # No separator and no leading uppercase: treated as camelCase, a single token stays itself.
    assert suggest_rename("svc", "account") == "account"


def test_underscore_wins_over_leading_case_when_both_are_present() -> None:
    assert suggest_rename("Open_Account", "open overdraft account") == "open_overdraft_account"


@pytest.mark.parametrize("identifier", ["", "   "])
def test_rejects_a_blank_identifier(identifier: str) -> None:
    with pytest.raises(ValueError, match=r"\Aidentifier must not be blank\Z"):
        suggest_rename(identifier, "open overdraft account")


@pytest.mark.parametrize("phrase", ["", "   "])
def test_rejects_a_blank_canonical_phrase(phrase: str) -> None:
    with pytest.raises(ValueError, match=r"\Acanonical_phrase must not be blank\Z"):
        suggest_rename("openAccount", phrase)
