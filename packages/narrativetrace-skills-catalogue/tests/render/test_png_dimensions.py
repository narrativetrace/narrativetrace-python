# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``png_dimensions`` reads width and height straight out of the ``IHDR`` chunk -- no imaging
library, so the package stays dependency-free."""

from __future__ import annotations

import struct

import pytest
from narrativetrace_skills.render.png_dimensions import png_dimensions

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_header(width: int, height: int) -> bytes:
    return SIGNATURE + struct.pack(">I4sII", 13, b"IHDR", width, height)


class TestPngDimensions:
    def test_reads_width_and_height_in_that_order(self) -> None:
        assert png_dimensions(_png_header(64, 32)) == (64, 32)

    def test_reads_the_ihdr_even_when_more_chunks_follow(self) -> None:
        assert png_dimensions(_png_header(48, 48) + b"\x00" * 100) == (48, 48)

    def test_reads_a_dimension_above_the_signed_32_bit_range(self) -> None:
        assert png_dimensions(_png_header(2**31, 1)) == (2**31, 1)

    def test_accepts_exactly_the_shortest_header(self) -> None:
        assert len(_png_header(1, 1)) == 24
        assert png_dimensions(_png_header(1, 1)) == (1, 1)

    def test_rejects_bytes_one_short_of_a_header(self) -> None:
        with pytest.raises(
            ValueError, match=r"\Anot a PNG: too short to hold a signature and IHDR\Z"
        ):
            png_dimensions(_png_header(1, 1)[:-1])

    def test_rejects_empty_bytes(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            png_dimensions(b"")

    def test_rejects_a_wrong_signature(self) -> None:
        with pytest.raises(ValueError, match=r"\Anot a PNG: bad signature\Z"):
            png_dimensions(b"\x89PNX\r\n\x1a\n" + _png_header(1, 1)[8:])

    def test_rejects_a_first_chunk_that_is_not_ihdr(self) -> None:
        header = SIGNATURE + struct.pack(">I4sII", 13, b"IDAT", 64, 64)
        with pytest.raises(ValueError, match=r"\Anot a PNG: first chunk is not IHDR\Z"):
            png_dimensions(header)
