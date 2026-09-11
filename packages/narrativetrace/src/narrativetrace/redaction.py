# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Name-based deny-list, plus value-shape masking, deciding whether an introspected field value
must be hidden.

``RedactionPolicy``. Reflective introspection is sensitive-data-by-default: a
dataclass/attrs/plain object or dict without a curated ``__str__`` would otherwise leak every
field value into traces, logs, and exports. This policy redacts values whose *field name*
matches a known-sensitive pattern (case-insensitive substring — deliberately erring toward
over-redaction), so secrets nested inside DTOs are hidden without a per-field annotation.

**The default vocabulary is multilingual and always on** — Spanish, Portuguese, French, German and
Chinese words sit in :data:`_DEFAULT_PATTERNS`/:data:`_TOKEN_BOUNDARY_PATTERNS` beside the
English ones, with no locale to select and nothing to opt into (the family standard, shared
by every NarrativeTrace runtime). A deny-list that only reads English hides a ``password``
field and shows the ``contraseña`` beside it, which is not a weaker guarantee but a
differently-distributed one: it protects whoever happens to name fields in the language the list
was written in. Names are folded through :func:`_canonical` — lower-cased, and accent-stripped
when non-ASCII — so the accented and unaccented spellings of a word are one pattern rather than
two.

**Value-shape masking** (adversarial-audit mirror, F3, 2026-09-02) is a second, independent axis:
:func:`~narrativetrace.secret_value_shapes.is_secret_shaped` catches a JWT/PAN/``Set-Cookie``-
shaped *value* regardless of what its field is named. ``DISABLED`` turns both axes off (the
documented opt-out); :meth:`RedactionPolicy.of_patterns` replaces the name list only and leaves
value masking on, because a custom name list is not an opinion about whether these bytes are a
credential.

**``pan``/``iban`` (and eight non-English words) are matched on identifier-token boundaries, not
as substrings** — see :meth:`RedactionPolicy.should_redact`. Every other pattern in this module
is a plain case-insensitive substring, which is safe for a word as distinctive as ``password``
but not for a three/four-letter word that is also a common substring of ordinary business names:
a naive ``"pan" in name.lower()`` redacts ``companyName``, ``expansionRatio``, ``panelId``,
``spanCount``, ``planId``, and ``japaneseAddress``; ``rut`` alone would redact ``truthValue`` and
``bruteForceAttempts``, ``senha`` would redact ``chosenHash``. A security default that blanks
ordinary business fields gets switched off wholesale, which is worse than the gap it closes.

**Narrow whenever in doubt**: Spanish ``clave`` and French ``carte`` are *not* in either pattern
set, even though both are short. A token match only protects a short word from *someone else's*
compound (``enclaveId``, ``cartesianProduct``); it cannot protect a codebase's own
``clavePrimaria`` or ``carteGraphique`` from a pattern that *is* their prefix. Both live in
:data:`_DEFAULT_PATTERNS` instead, spelled out as the specific compounds that are credentials
(``claveacceso``, ``clavesecreta``, ``cartebancaire``, ``numerocarte``).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import ClassVar

from narrativetrace.secret_value_shapes import is_secret_shaped

REDACTED_MARKER = "[REDACTED]"
"""Marker emitted in place of a redacted value (matches the ``@not_traced`` marker)."""

_DEFAULT_PATTERNS = frozenset(
    {
        # English
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
        # Added 2026-09-10, family-wide audit (found absent from all five runtimes' deny-lists):
        "passphrase",
        "otp",
        "bearer",
        "accesskey",
        "access_key",
        "socialsecurity",
        "social_security",
        "socialsecuritynumber",
        "taxid",
        "tax_id",
        # ("pan", "iban" live in _TOKEN_BOUNDARY_PATTERNS below, not here -- see that set's
        # docstring for why they, and the eight non-English words beside them, are matched as a
        # whole identifier token instead of a substring.)
        # Spanish: contraseña, tarjeta, cédula -- written folded, matched either way via
        # _canonical
        "contrasena",
        "tarjeta",
        "cedula",
        # Spanish: bare "clave" was narrowed away (family ruling 2026-09-03) -- it matched
        # clavePrimaria and claveForanea, ordinary database terms, not credentials. These two
        # compounds are the unit instead; both spellings, because the underscore is part of the
        # name being matched.
        "claveacceso",
        "clave_acceso",
        "clavesecreta",
        "clave_secreta",
        # Portuguese: cartão
        "cartao",
        # French: both spellings, because the underscore is part of the name being matched
        "motdepasse",
        "mot_de_passe",
        # French: bare "carte" was narrowed away (family ruling 2026-09-03) -- it matched
        # carteGraphique and carteRoutiere, ordinary identifiers, not credentials. These two
        # compounds are the unit instead; both spellings, same reason as above.
        "cartebancaire",
        "carte_bancaire",
        "numerocarte",
        "numero_carte",
        # Chinese: 密码 (mima, "password") and 身份证 (identity card), plus the pinyin a
        # codebase without CJK identifiers writes instead
        "密码",
        "身份证",
        "shenfenzheng",
        # German: Passwort/Kennwort ("password"), added 2026-09-10, family-wide audit
        "passwort",
        "kennwort",
    }
)

_TOKEN_BOUNDARY_PATTERNS = frozenset(
    {
        # English: three/four letters, common substrings of ordinary business names -- see the
        # module docstring.
        "pan",
        "iban",
        # Every non-English word below earned its place by colliding with a real business field,
        # which is why the set is not simply "the short ones": "rut" is inside "truth", "brute"
        # and "scrutiny"; "cuit" inside "circuit" and "biscuit"; "dni" inside "midnight"; "nir"
        # inside "nirvana"; "mima" inside "semiMajorAxis" once the case boundary is lower-cased
        # away. "senha" is the subtle one -- no English word contains it, but "chosenHash" and
        # "frozenHash" do, across the camelCase seam. "cpf" and "cnpj" are here for length alone.
        "rut",
        "cuit",
        "dni",
        "senha",
        "cpf",
        "cnpj",
        "nir",
        "mima",
    }
)
"""Patterns too short to be safe as a substring test — matched as a whole identifier token (or
the whole field name, for a run-together case like ``IbAn``) instead. See module docstring."""

_TOKEN_SPLIT = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z0-9]+")
_NON_ALNUM = re.compile(r"[^0-9A-Za-z]+")
_MARK_CATEGORIES = ("Mn", "Mc", "Me")


def _canonical(text: str) -> str:
    """Case- and accent-folds ``text`` the way the deny-list matches it: lower-cased, and (only
    when it carries a non-ASCII character) NFD-normalised with combining marks stripped, so the
    accented and unaccented spellings of a word are one pattern rather than two. Mirrors Java's
    ``SecretValueShapes.canonical`` -- Python's stdlib ``re`` has no ``\\p{M}`` Unicode-category
    escape, so combining marks are dropped by :func:`unicodedata.category` instead of a regex."""
    lower = text.lower()
    if lower.isascii():
        return lower
    decomposed = unicodedata.normalize("NFD", lower)
    return "".join(
        char for char in decomposed if unicodedata.category(char) not in _MARK_CATEGORIES
    )


def _identifier_tokens(name: str) -> frozenset[str]:
    """Splits ``name`` into its identifier words -- on any non-alphanumeric run, and (within an
    alphanumeric run) on a lower-to-upper or acronym-to-word case transition -- each folded
    through :func:`_canonical`.

    ASCII-boundary splitting by design: every :data:`_TOKEN_BOUNDARY_PATTERNS` entry is itself
    plain ASCII (the non-English words earned token-boundary treatment for being *short*, not
    for being non-Latin script), so a CJK or accented compound never needs splitting -- a
    Chinese or Spanish deny-list word is matched as a whole-string substring instead, in both
    this runtime and the Java original, which is what :data:`_DEFAULT_PATTERNS` is for. A field
    named exactly ``密码`` or ``contraseña`` -- legal Python identifiers, unlike Java's ASCII-only
    convention -- still matches, through the substring pass in :meth:`RedactionPolicy.should_redact`
    below, before this function is ever called.
    """
    tokens: list[str] = []
    for part in _NON_ALNUM.split(name):
        if part:
            tokens.extend(_canonical(match.group(0)) for match in _TOKEN_SPLIT.finditer(part))
    return frozenset(tokens)


class RedactionPolicy:
    """Case-insensitive substring deny-list over field names, plus value-shape masking."""

    DEFAULT: ClassVar[RedactionPolicy]
    DISABLED: ClassVar[RedactionPolicy]

    def __init__(self, patterns: Iterable[str], *, mask_secret_shaped_values: bool = True) -> None:
        self._patterns = frozenset(_canonical(p) for p in patterns)
        self._mask_secret_shaped_values = mask_secret_shaped_values

    @property
    def patterns(self) -> frozenset[str]:
        """The (case- and accent-folded) deny-list patterns."""
        return self._patterns

    @classmethod
    def of_patterns(cls, patterns: Iterable[str]) -> RedactionPolicy:
        """Creates a policy with a custom pattern set, replacing the defaults entirely (value-shape
        masking stays on — a custom name list is not an opinion about whether these bytes are a
        credential)."""
        return cls(patterns)

    def should_redact(self, field_name: str | None) -> bool:
        """Whether ``field_name`` matches any deny-list pattern.

        Every pattern is a case- and accent-insensitive substring test (see :func:`_canonical`)
        except :data:`_TOKEN_BOUNDARY_PATTERNS` (``pan``, ``iban``, and eight non-English words),
        which match only a whole identifier token (``card_pan``, ``rutCliente``) or the whole
        field name (catching a run-together case like ``IbAn``, which token-splitting alone would
        see as ``ib`` + ``an``) — see module docstring.
        """
        if field_name is None:
            return False
        canonical = _canonical(field_name)
        tokens: frozenset[str] | None = None
        for pattern in self._patterns:
            if pattern not in _TOKEN_BOUNDARY_PATTERNS:
                if pattern in canonical:
                    return True
                continue
            if canonical == pattern:
                return True
            tokens = _identifier_tokens(field_name) if tokens is None else tokens
            if pattern in tokens:
                return True
        return False

    def should_redact_value(self, value: str) -> bool:
        """Whether ``value``'s own structure marks it as a secret, independent of field name.

        ``False`` for :data:`DISABLED` (both redaction axes off) regardless of the value's shape.
        """
        return self._mask_secret_shaped_values and is_secret_shaped(value)

    def is_redacted(self, member_name: str, *, annotated: bool) -> bool:
        """The single redaction rule for a named member: an explicit ``@not_traced`` annotation
        always redacts, and otherwise the name-based deny-list decides.

        Every surface that can name a member — reflective introspection in
        :mod:`narrativetrace.rendering`, and :mod:`narrativetrace.template` path resolution —
        calls this one method, so a member is redacted the same way regardless of which surface
        names it.
        """
        return annotated or self.should_redact(member_name)


RedactionPolicy.DEFAULT = RedactionPolicy(_DEFAULT_PATTERNS | _TOKEN_BOUNDARY_PATTERNS)
"""Secure default: redacts values for common sensitive field-name patterns (substring and
whole-identifier-token alike, multilingual), plus JWT/PAN/``Set-Cookie``-shaped values regardless
of field name."""

RedactionPolicy.DISABLED = RedactionPolicy(frozenset(), mask_secret_shaped_values=False)
"""Opt-out policy that redacts nothing by name or by value shape (annotations are still honoured
elsewhere)."""
