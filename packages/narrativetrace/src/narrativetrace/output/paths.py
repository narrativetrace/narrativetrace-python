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


def _fnv1a_hex(text: str) -> str:
    """FNV-1a over ``text``'s UTF-8 bytes, as eight lowercase hex digits.

    Not Python's built-in ``hash()``: string hashing is salted per-process by default
    (``PYTHONHASHSEED``), and this disambiguator must be stable across runs so the same name
    always resolves to the same artifact. It is not a security boundary, only a
    collision-avoidance one -- mirrors the Swift port's ``OutputDirectoryResolver.hexHash``,
    chosen there for the same reason (Swift's own ``Hasher`` is also randomized per process).
    """
    digest = 0x811C9DC5
    for byte in text.encode("utf-8"):
        digest ^= byte
        digest = (digest * 0x01000193) & 0xFFFFFFFF
    return f"{digest:08x}"


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
    suffix = "_" + _fnv1a_hex(slug)
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
