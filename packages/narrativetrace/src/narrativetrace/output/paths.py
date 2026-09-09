# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""On-disk layout and slug/extension rules for test trace artifacts.

``OutputDirectoryResolver`` + ``TraceTestSupport`` format→extension mapping.

Both halves of a path are sanitized here, and neither is trusted to arrive safe: ``TraceArtifact``
callers are not all deriving names from ``Class.getName()``/a test-method name -- a scenario name
or an HTTP route reaches these functions in real integrations, so a name is data, not an
identifier. Mirrors Java's ``OutputDirectoryResolver``.
"""

from __future__ import annotations

import re
from pathlib import Path

_CAMEL_BOUNDARY = re.compile(r"([a-z])([A-Z])")
_NON_SLUG = re.compile(r"[^a-z0-9_]")

_EXTENSIONS = {
    "text": ".txt",
    "mermaid": ".mmd",
    "plantuml": ".puml",
}

_PATH_UNSAFE_SEPARATORS = frozenset("/\\")

_PATH_UNSAFE_NONCHARACTERS = frozenset({0xFFFE, 0xFFFF})
"""The two BMP noncharacters legal UTF-8 encodes but a real filesystem this library ships to can
still refuse: macOS/APFS raises ``OSError: Illegal byte sequence`` from `mkdir`/`open` on a name
carrying either one -- found running this port's own corpus locally, on the platform the shared
Java spec repo's dev container never touches (release-retrospective rule 1: verification does not
transfer across environments). The same two code points frontmatter's ``yaml_safe`` already
escapes for the same reason, one layer up."""

_MAX_COMPONENT_BYTES = 255
"""The longest a single path element may be, in *bytes*: what ext4, XFS, APFS and NTFS all
allow. Bytes, not characters, on every filesystem this library writes to except NTFS (which
counts UTF-16 units and is therefore never the tighter of the two for the names seen here) --
counting characters would pass a 200-character CJK name and then fail the write at 600 bytes."""

_SUFFIX_RESERVE_BYTES = 16
"""Bytes held back from a file slug for the suffix a writer appends to it. The longest shipped
here is ``.canonical.json`` at 15; ``.puml``/``.json`` are 5, ``.txt``/``.mmd`` 4, ``.md`` 3. 16
leaves room for one more without this constant having to change."""


def _is_path_safe(char: str) -> bool:
    """A lone surrogate is refused for the same reason a control character is: it encodes to no
    well-formed UTF-8 bytes, so a filesystem call can raise or mis-encode before the file is ever
    written. A BMP noncharacter is refused for a related but distinct reason: it encodes to
    well-formed UTF-8 bytes, but not every filesystem this library writes to accepts them."""
    codepoint = ord(char)
    is_control = codepoint <= 0x1F or 0x7F <= codepoint <= 0x9F
    is_surrogate = 0xD800 <= codepoint <= 0xDFFF
    return (
        not is_control
        and not is_surrogate
        and codepoint not in _PATH_UNSAFE_NONCHARACTERS
        and char not in _PATH_UNSAFE_SEPARATORS
    )


def _to_directory_slug(simple_name: str) -> str:
    """Everything a path cannot carry, replaced: separators (which would write outside the
    directory the caller was given -- a ``../../etc/passwd`` class name used to reach ``Path``
    construction unfiltered, and a name whose only ``.`` sat inside a leading ``..`` resolved to
    an *absolute* path, which a ``/`` join takes as the whole answer) and control
    characters/lone surrogates (which a filesystem call cannot round-trip safely). Nothing else
    -- a class name keeps its own spelling, Unicode letters included. Deliberately narrower than
    :func:`file_slug`: this only removes what a path cannot carry, so ``OrderServiceTest`` still
    resolves to ``OrderServiceTest`` and no existing artifact -- or approved baseline beside it
    -- moves.
    """
    safe = "".join(char if _is_path_safe(char) else "_" for char in simple_name)
    named = "unnamed" if not safe or all(c == "." for c in safe) else safe
    return _capped(named, _MAX_COMPONENT_BYTES)


_UTF16_SUPPLEMENTARY_BASE = 0x10000
_UTF16_HIGH_SURROGATE_BASE = 0xD800
_UTF16_LOW_SURROGATE_BASE = 0xDC00
_UTF16_LOW_TEN_BITS = 0x3FF
_UINT32_MASK = 0xFFFFFFFF


def _java_string_hash(text: str) -> int:
    """Java's specified ``String.hashCode()``: ``h = 31*h + c`` over UTF-16 *code units*, as an
    unsigned 32-bit value (Java's signed overflow and this mask produce the same bit pattern, and
    that bit pattern -- not its signed value -- is what gets formatted as hex below).

    Not Python's built-in ``hash()``: string hashing is salted per-process by default
    (``PYTHONHASHSEED``), and this disambiguator must be stable across runs so the same name
    always resolves to the same artifact. Java's formula has no such randomization and is
    specified to give the same result forever, which is why the family standardized on
    reimplementing it here rather than each runtime inventing its own stable hash -- one hashing
    scheme, not one per port (dotnet reimplements the same formula for the same reason: ``.NET``
    also randomizes ``string.GetHashCode()`` per process).

    A Python ``str`` iterates by Unicode code point, not UTF-16 code unit, so a supplementary
    character (a code point at or above U+10000, one Java ``char`` cannot hold) is expanded to
    the surrogate pair Java's own UTF-16-backed ``String`` would already store it as. A code
    point already at or below U+FFFF -- including a lone surrogate, which Python permits as a
    scalar value and Java permits as an unpaired ``char`` -- is one code unit in both, so it is
    hashed directly with no pairing.
    """
    digest = 0
    for char in text:
        code_point = ord(char)
        if code_point >= _UTF16_SUPPLEMENTARY_BASE:
            offset = code_point - _UTF16_SUPPLEMENTARY_BASE
            high_surrogate = _UTF16_HIGH_SURROGATE_BASE + (offset >> 10)
            low_surrogate = _UTF16_LOW_SURROGATE_BASE + (offset & _UTF16_LOW_TEN_BITS)
            digest = (31 * digest + high_surrogate) & _UINT32_MASK
            digest = (31 * digest + low_surrogate) & _UINT32_MASK
        else:
            digest = (31 * digest + code_point) & _UINT32_MASK
    return digest


def _truncate_to_bytes(value: str, max_bytes: int) -> str:
    """The longest prefix of ``value`` that encodes to at most ``max_bytes`` UTF-8 bytes, cut on
    a character boundary so a multi-byte code point is never split in half."""
    encoded = value.encode("utf-8")[: max(0, max_bytes)]
    return encoded.decode("utf-8", errors="ignore")


def _capped(slug: str, max_bytes: int) -> str:
    """``slug``, shortened to fit ``max_bytes`` when it does not already.

    A name longer than the filesystem allows makes a write raise ``OSError`` -- an observability
    failure becoming an application failure, which this library does not do. Truncation alone is
    a silent overwrite: two long names sharing a prefix would land on one artifact, and one
    test's approved baseline would then judge another's trace. The truncated form keeps an
    eight-hex-character hash of the whole slug as a disambiguator, so the same name always maps
    to the same artifact and two different long names essentially never collide.

    Nothing under the limit is touched, so no existing artifact -- or approved baseline beside it
    -- moves.
    """
    if len(slug.encode("utf-8")) <= max_bytes:
        return slug
    suffix = "_" + f"{_java_string_hash(slug):08x}"
    budget = max_bytes - len(suffix.encode("utf-8"))
    return _truncate_to_bytes(slug, budget) + suffix


def file_slug(name: str) -> str:
    """camelCase/snake → snake, then non-``[a-z0-9_]`` → ``_``, capped to fit a path element."""
    snake = _CAMEL_BOUNDARY.sub(r"\1_\2", name).lower()
    slug = _NON_SLUG.sub("_", snake)
    return _capped(slug, _MAX_COMPONENT_BYTES - _SUFFIX_RESERVE_BYTES)


def extension_for_format(fmt: str) -> str:
    """Maps a format name to its extension, case-insensitively (``markdown``/unknown → ``.md``).

    Case folding matches Java ``TraceTestSupport.extensionForFormat``, which switches on
    ``format.toLowerCase()`` — so an env value of ``PlantUML`` resolves like ``plantuml``.
    """
    return _EXTENSIONS.get(fmt.lower(), ".md")


def _simple_name(class_name: str) -> str:
    return class_name.rsplit(".", 1)[-1] if "." in class_name else class_name


def _directory_segment(class_name: str) -> str:
    return _to_directory_slug(_simple_name(class_name))


def trace_directory(base_dir: Path, class_name: str) -> Path:
    """``<base>/traces/<SimpleClass>``."""
    return base_dir / "traces" / _directory_segment(class_name)


def trace_file(base_dir: Path, class_name: str, method_name: str) -> Path:
    """``<base>/traces/<SimpleClass>/<slug>.md``."""
    return trace_directory(base_dir, class_name) / f"{file_slug(method_name)}.md"


def diagram_file(base_dir: Path, class_name: str, method_name: str) -> Path:
    """``<base>/diagrams/<SimpleClass>/<slug>.mmd`` (the coupled markdown diagram extra)."""
    return base_dir / "diagrams" / _directory_segment(class_name) / f"{file_slug(method_name)}.mmd"
