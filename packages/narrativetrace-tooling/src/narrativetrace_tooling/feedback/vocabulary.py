# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The names and the credential shapes the value-free gate refuses — the DATA half of the name and
shape rules.

Ports Java ``SecretVocabulary``. INTENT: the runtime's own deny-list
(``narrativetrace.redaction.RedactionPolicy``, multilingual, always on) is the authority on what a
sensitive field is called. This library declares zero dependencies and may never link against that
runtime, so the vocabulary is restated here as data and ``narrativetrace-security-tests`` — the one
package that may see both — asserts the only implication that matters: every name the runtime
redacts is also refused here. Drift is a build failure, not a leak discovered in a public issue.

**@llmNote** Matching here is COARSER than the runtime's on purpose. The runtime distinguishes
substring terms from identifier-token terms (``pan`` as a substring redacts ``companyName``):
blanking an ordinary business field is how a team switches redaction off entirely. This gate blanks
nothing — it refuses to file a report and names the rule — so a near miss costs a sentence, and the
only expensive mistake is the one that files a credential. Every term below is therefore a plain
substring of the canonical key.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

TERMS: Final[tuple[str, ...]] = (
    # credentials
    "password",
    "passwd",
    "passphrase",
    "contrasena",
    "claveacceso",
    "clave_acceso",
    "clavesecreta",
    "clave_secreta",
    "senha",
    "motdepasse",
    "mot_de_passe",
    "passwort",
    "kennwort",
    "密码",
    "mima",
    "token",
    "apikey",
    "api_key",
    "accesskey",
    "access_key",
    "bearer",
    "secret",
    "credential",
    "privatekey",
    "private_key",
    "authorization",
    "otp",
    "mfacode",
    "mfa_code",
    "totp",
    # session
    "sessionid",
    "session_id",
    "cookie",
    "setcookie",
    "set_cookie",
    "jwt",
    # payment
    "cardnumber",
    "card_number",
    "pan",
    "tarjeta",
    "cartao",
    "cartebancaire",
    "carte_bancaire",
    "numerocarte",
    "numero_carte",
    "cvv",
    "accountnumber",
    "account_number",
    "routingnumber",
    "routing_number",
    "iban",
    # national ids
    "ssn",
    "socialsecurity",
    "social_security",
    "socialsecuritynumber",
    "taxid",
    "tax_id",
    "rut",
    "cuit",
    "dni",
    "cedula",
    "cpf",
    "cnpj",
    "nir",
    "身份证",
    "shenfenzheng",
)
"""Every deny-listed term, already canonical (lower case, no diacritics). Matched as a substring of
the canonical form of whatever key is being assigned a value."""

SHAPES: Final[tuple[re.Pattern[str], ...]] = (
    # A JWT, anchored on the base64url encoding of a JSON object's opening — `{"`.
    re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}"),
    # A PEM private key block header.
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # Named credential prefixes: the five whose shape is the credential.
    re.compile(r"\bghp_[A-Za-z0-9]{8,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{8,}"),
    # A Chilean RUT, printed with or without its thousands dots.
    re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]\b"),
    # A Brazilian CPF.
    re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    # A Brazilian CNPJ.
    re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
    # A Spanish DNI or NIE.
    re.compile(r"\b[XYZxyz]?\d{7,8}-?[A-Za-z]\b"),
    # A French NIR, bare or in the spaced form a card is printed in, Corsica included.
    re.compile(r"\b[12]\s?\d{2}\s?\d{2}\s?(\d{2}|\d?[AB])\s?\d{3}\s?\d{3}\s?\d{2}\b"),
    # A Chinese resident identity card.
    re.compile(r"\b\d{17}[\dXx]\b"),
    # A payment card number's digit length.
    re.compile(r"\b\d{13,19}\b"),
)
"""The shapes a value gives itself away by, STRUCTURALLY — no checksum is verified here.

**@llmNote** Deliberately not a copy of the runtime's checksum-exact matchers
(``narrativetrace.national_id_shapes`` verifies six of them). Copying six check-digit algorithms
into a library that may not link the one that already has them is how two implementations start
disagreeing; a shape that is a SUPERSET of theirs cannot. The price is paid in the right currency: a
checksum-failing lookalike is refused with a named rule instead of being filed."""

_COMBINING_MARK_CATEGORIES: Final = ("Mn", "Mc", "Me")


def canonical(text: str) -> str:
    """Lower case with diacritics folded away — ``contraseña``, ``contrasena`` and the decomposed
    ``contrasen`` + U+0303 a Mac filesystem hands back all become one string.

    Separators are deliberately NOT stripped, which is why ``api_key`` and ``apikey`` are two terms
    in :data:`TERMS` rather than one. Mirrors the runtime's own
    ``narrativetrace.redaction._canonical``: Python's ``re`` has no ``\\p{M}`` escape, so combining
    marks are dropped through :func:`unicodedata.category` rather than a regex.
    """
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(
        char for char in decomposed if unicodedata.category(char) not in _COMBINING_MARK_CATEGORIES
    )


def names_a_secret(key: str) -> bool:
    """Whether the canonical form of this key contains any deny-listed term."""
    folded = canonical(key)
    return any(term in folded for term in TERMS)


def contains_a_secret_shape(text: str) -> bool:
    """Whether any secret-shaped value appears anywhere in this text."""
    return any(shape.search(text) is not None for shape in SHAPES)
