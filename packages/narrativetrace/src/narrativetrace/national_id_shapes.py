# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Recognises national identity numbers by their own check digits, whatever the field is called.

``NationalIdShapes``. :mod:`~narrativetrace.secret_value_shapes` already answers "are
these bytes a credential?" for a JWT, a card number and a ``Set-Cookie``. A national identity
number is the same question in a different jurisdiction, and it is the one piece of sensitive
data whose *name* is most often in a language the deny-list is read in but not written in --
``numero``, ``documento``, ``id``. The value's own checksum does not care what language the
field name is in, which is why these shapes are language-neutral and on by default for everyone
(family standard, ported from the Java runtime's ``NationalIdShapes``).

Every matcher here is a checksum, never a length-and-digits guess, and every one is gated by a
cheap regex before any arithmetic runs -- the same discipline the Luhn PAN matcher
(:mod:`~narrativetrace.secret_value_shapes`) uses. A scheme without a check digit (the pre-1999
15-digit Chinese id, a bare Spanish DNI with the letter dropped) is deliberately absent: it would
be indistinguishable from an order number, and a security default that blanks ordinary business
fields is one teams switch off entirely.

**The Chilean RUT requires its verifier separator.** Chile writes a RUT as ``12.345.678-5`` or
``12345678-5``, and the dash is what distinguishes it from any other eight-digit number;
accepting a bare nine-digit run would redact roughly one in eleven of every order and invoice
number in the world, which is the false-positive budget this module exists to avoid. Dots are
optional, the dash is not.

**CPF and CNPJ reject repeated-digit strings** (``00000000000``, ``11111111111``) before the
checksum, because every one of them satisfies both check digits and none of them is a real
document -- they are the placeholder a form writes when it has none.
"""

from __future__ import annotations

import re

_RUT = re.compile(r"(?:\d{1,2}\.\d{3}\.\d{3}|\d{7,8})-[0-9kK]")
"""Chile: 7-8 digits, optional thousands dots, and a mod-11 verifier that may be ``K``."""

_CPF = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11}")
"""Brazil: 11 digits, written bare or as ``NNN.NNN.NNN-NN``."""

_CNPJ = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14}")
"""Brazil: 14 digits, written bare or as ``NN.NNN.NNN/NNNN-NN``."""

_SPANISH_ID = re.compile(r"(?:[XYZ]\d{7}|\d{8})-?[A-Z]", re.IGNORECASE)
"""Spain: a DNI is 8 digits plus a letter; a NIE swaps the leading digit for ``X``/``Y``/``Z``."""

_NIR = re.compile(r"[1-478]\d{4}(?:\d{2}|2[AB])\d{8}", re.IGNORECASE)
"""France: 13-character body plus a 2-digit key. Only the department (positions 6-7) may be
non-numeric, and only as Corsica's ``2A``/``2B``."""

_CHINESE_ID = re.compile(r"\d{17}[0-9Xx]")
"""China: the post-1999 resident identity card, 17 digits and a check character."""

_PUNCTUATION = re.compile(r"[.\-/]")
_SPACE = re.compile(" ")

_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
"""The Spanish check letter, indexed by the document number modulo 23."""

_NIE_PREFIXES = "XYZ"
"""A NIE's leading letter stands for a digit: ``X`` = 0, ``Y`` = 1, ``Z`` = 2."""

_CHINESE_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)

_CHINESE_CHECK_CHARACTERS = "10X98765432"
"""The Chinese check character, indexed by the weighted sum modulo 11."""

_EARLIEST_BIRTH_YEAR = 1900
_LATEST_BIRTH_YEAR = 2100


def is_national_id(value: str) -> bool:
    """Whether ``value`` is a national identity number that passes its own checksum.

    ``value`` is a trimmed rendered value. Returns ``True`` for a valid Chilean RUT, Brazilian
    CPF or CNPJ, Spanish DNI or NIE, French NIR, or Chinese resident identity card.
    """
    return (
        _is_rut(value)
        or _is_cpf(value)
        or _is_cnpj(value)
        or _is_spanish_id(value)
        or _is_french_nir(value)
        or _is_chinese_resident_id(value)
    )


def _is_rut(value: str) -> bool:
    if not _RUT.fullmatch(value):
        return False
    compact = _PUNCTUATION.sub("", value)
    body = compact[:-1]
    return compact[-1].lower() == _rut_verifier(body)


def _rut_verifier(body: str) -> str:
    """Chile's mod 11: weights 2..7 cycling from the right, ``10`` written ``K``."""
    total = 0
    weight = 2
    for char in reversed(body):
        total += int(char) * weight
        weight = 2 if weight == 7 else weight + 1
    rest = 11 - (total % 11)
    if rest == 11:
        return "0"
    return "k" if rest == 10 else str(rest)


def _is_cpf(value: str) -> bool:
    if not _CPF.fullmatch(value):
        return False
    digits = _PUNCTUATION.sub("", value)
    return (
        not _is_repeated_digit(digits)
        and _cpf_check_digit(digits, 9) == int(digits[9])
        and _cpf_check_digit(digits, 10) == int(digits[10])
    )


def _cpf_check_digit(digits: str, length: int) -> int:
    """Brazil's mod 11 for the CPF: weights count down from ``length + 1`` to 2."""
    total = sum(int(digits[i]) * (length + 1 - i) for i in range(length))
    return _check_digit_from_remainder(total)


def _is_cnpj(value: str) -> bool:
    if not _CNPJ.fullmatch(value):
        return False
    digits = _PUNCTUATION.sub("", value)
    return (
        not _is_repeated_digit(digits)
        and _cnpj_check_digit(digits, 12) == int(digits[12])
        and _cnpj_check_digit(digits, 13) == int(digits[13])
    )


def _cnpj_check_digit(digits: str, length: int) -> int:
    """Brazil's mod 11 for the CNPJ: weights 2..9 cycling from the right."""
    total = 0
    weight = 2
    for i in range(length - 1, -1, -1):
        total += int(digits[i]) * weight
        weight = 2 if weight == 9 else weight + 1
    return _check_digit_from_remainder(total)


def _check_digit_from_remainder(total: int) -> int:
    """Both Brazilian schemes share the final step: a remainder below two means a zero digit."""
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def _is_repeated_digit(digits: str) -> bool:
    return all(char == digits[0] for char in digits[1:])


def _is_spanish_id(value: str) -> bool:
    if not _SPANISH_ID.fullmatch(value):
        return False
    upper = _PUNCTUATION.sub("", value.upper())
    body = upper[:-1]
    prefix = _NIE_PREFIXES.find(body[0])
    number = body if prefix < 0 else str(prefix) + body[1:]
    return _DNI_LETTERS[int(number) % 23] == upper[-1]


def _is_french_nir(value: str) -> bool:
    compact = _SPACE.sub("", value)
    if not _NIR.fullmatch(compact):
        return False
    body = compact[:13].upper().replace("2A", "19").replace("2B", "18")
    return int(compact[13:]) == 97 - (int(body) % 97)


def _is_chinese_resident_id(value: str) -> bool:
    if not _CHINESE_ID.fullmatch(value) or not _has_plausible_birth_date(value):
        return False
    total = sum(int(value[i]) * weight for i, weight in enumerate(_CHINESE_WEIGHTS))
    return _CHINESE_CHECK_CHARACTERS[total % 11] == value[17].upper()


def _has_plausible_birth_date(value: str) -> bool:
    """Positions 6-13 (0-indexed) of a Chinese resident id are the holder's birth date. Checking
    it costs three integer parses and removes most of what the check character alone would let
    through -- a one-in-eleven hit rate on eighteen-digit numbers is otherwise the whole
    false-positive budget."""
    year = int(value[6:10])
    month = int(value[10:12])
    day = int(value[12:14])
    return (
        _EARLIEST_BIRTH_YEAR <= year <= _LATEST_BIRTH_YEAR and 1 <= month <= 12 and 1 <= day <= 31
    )
