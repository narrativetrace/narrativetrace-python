# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Reads a PNG's width and height straight out of its ``IHDR`` chunk -- no imaging library, so the
catalogue package stays dependency-free. ``scripts/openai_plugin_pack.py`` uses this to check the
two listing icons are square and large enough without decoding a pixel."""

from __future__ import annotations

import struct

_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_IHDR_END = len(_SIGNATURE) + 4 + 4 + 8  # signature, chunk length, chunk type, width + height


def png_dimensions(png: bytes) -> tuple[int, int]:
    """``(width, height)`` in pixels. Raises ``ValueError`` for bytes that are not a PNG header:
    too short to hold the signature and ``IHDR``, a wrong signature, or a first chunk that is not
    ``IHDR``."""
    if len(png) < _IHDR_END:
        raise ValueError("not a PNG: too short to hold a signature and IHDR")
    if not png.startswith(_SIGNATURE):
        raise ValueError("not a PNG: bad signature")
    if png[12:16] != b"IHDR":
        raise ValueError("not a PNG: first chunk is not IHDR")
    width, height = struct.unpack(">II", png[16:_IHDR_END])
    return width, height
