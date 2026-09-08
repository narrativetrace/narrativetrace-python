# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Structural detectors for secret-shaped string *values*, independent of field name.

``SecretValueShapes`` (adversarial-audit mirror, F3, 2026-09-02). Deliberately narrow:
each detector is a structural check (a checksum, a fixed token count, a named attribute), never an
entropy or "looks random" heuristic — a value blanked by guesswork is a hole in the narrative the
reader cannot see and cannot switch off per-value. False positives are pinned in tests in the
direction the report requires: an order number that fails Luhn stays visible.

National identity numbers are a fourth shape, kept in their own module
(:mod:`~narrativetrace.national_id_shapes`) because they are six checksums rather than one
matcher; they are language-neutral by construction — a CPF is a CPF whatever the field holding it
is called, which is the point: the name deny-list can be read in a language it was not written
in, and a checksum cannot (family standard, ported from the Java runtime).
"""

from __future__ import annotations

from narrativetrace.national_id_shapes import is_national_id

_JWT_HEADER_PREFIX = "eyJ"
_JWT_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")

_PAN_MIN_DIGITS = 13
_PAN_MAX_DIGITS = 19
_PAN_SEPARATORS = frozenset(" -")

_COOKIE_ATTRIBUTES = frozenset(
    {"path", "domain", "secure", "httponly", "samesite", "max-age", "expires"}
)


def is_jwt_like(value: str) -> bool:
    """Three base64url segments, the first starting ``eyJ`` (base64url of ``{"``, present in
    every real JWT header). A dotted hostname or an ``a.b.c`` value never starts a segment with
    it, keeping the false-positive rate near zero without inspecting the payload's structure."""
    segments = value.split(".")
    if len(segments) != 3:
        return False
    if not all(segments):
        return False
    if not segments[0].startswith(_JWT_HEADER_PREFIX):
        return False
    return all(_is_base64url(segment) for segment in segments)


def _is_base64url(segment: str) -> bool:
    return all(char in _JWT_ALPHABET for char in segment)


def is_pan_like(value: str) -> bool:
    """13-19 digits, ``[ -]`` separators allowed, Luhn-valid. A structural checksum rather than a
    length guess -- the one accepted false positive is a card-length identifier that happens to
    satisfy Luhn (~1 in 10), inherent to detecting PANs at all."""
    if not value or not (value[0].isdigit() and value[-1].isdigit()):
        return False
    if not all(char.isdigit() or char in _PAN_SEPARATORS for char in value):
        return False
    digits = [char for char in value if char.isdigit()]
    if not (_PAN_MIN_DIGITS <= len(digits) <= _PAN_MAX_DIGITS):
        return False
    return _luhn_valid(digits)


def _luhn_valid(digits: list[str]) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def is_set_cookie_like(value: str) -> bool:
    """A ``name=value;`` pair followed by at least one named RFC 6265 attribute. Requiring the
    attribute (not just ``;``-joined pairs) keeps an ordinary ``"name=Ada; age=36"`` value
    visible -- only a cookie header actually carries ``Path=``/``Secure``/``HttpOnly``/etc."""
    parts = [part.strip() for part in value.split(";")]
    if len(parts) < 2:
        return False
    name, _, cookie_value = parts[0].partition("=")
    if not name.strip() or not cookie_value.strip():
        return False
    return any(_is_cookie_attribute(part) for part in parts[1:])


def _is_cookie_attribute(part: str) -> bool:
    attr_name = part.split("=", 1)[0].strip().lower()
    return attr_name in _COOKIE_ATTRIBUTES


def is_secret_shaped(value: str) -> bool:
    """Whether ``value``'s own structure -- not its field name -- marks it as a secret: a JWT, a
    Luhn-valid PAN, a ``Set-Cookie`` string, or a national identity number that passes its own
    checksum."""
    return (
        is_jwt_like(value)
        or is_pan_like(value)
        or is_set_cookie_like(value)
        or is_national_id(value)
    )
