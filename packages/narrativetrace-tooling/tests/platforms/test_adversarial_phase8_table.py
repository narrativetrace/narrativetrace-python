# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial edge cases for the platform table's row and pointer constructors (Phase 8,
platform pointers).

Written to find what the existing table tests do not pin: a pointer path that names the project
itself, a verification date that is a date only by shape, marker paths that are empty or leave the
project, and the id/lane rules at their boundaries.
"""

from __future__ import annotations

import pytest

from narrativetrace_tooling.platforms.table import (
    MANUAL,
    ManagedSection,
    NoPointer,
    PlatformRow,
)


def _row(
    *,
    markers: tuple[str, ...] = (".some",),
    verified: str = "2026-10-10",
    lane: str = MANUAL,
) -> PlatformRow:
    return PlatformRow(
        "some-platform",
        "Name",
        markers,
        NoPointer(),
        "install",
        "finds",
        lane,
        verified,
    )


class TestPointerPaths:
    def test_a_managed_section_may_not_name_the_project_directory_itself(self) -> None:
        """``.`` stays inside the project, but it is the project, not a file a section can live
        in: a pointer written there would be a read or write of the directory."""
        with pytest.raises(ValueError, match="project-relative"):
            ManagedSection(".")


class TestVerificationDates:
    def test_a_date_must_name_a_real_calendar_day(self) -> None:
        """``yyyy-mm-dd`` is the documented contract; month 13 is no date, however well shaped."""
        with pytest.raises(ValueError, match="yyyy-mm-dd"):
            _row(verified="2026-13-45")

    def test_a_date_is_ascii_digits_not_any_unicode_digit(self) -> None:
        """Arabic-Indic digits are ``\\d`` under Python's Unicode regex, but not a date a reader can
        compare against the vendor pages."""
        with pytest.raises(ValueError, match="yyyy-mm-dd"):
            _row(verified="\u0662\u0660\u0662\u0666-\u0661\u0660-\u0661\u0660")


class TestMarkerPaths:
    def test_a_marker_path_may_not_be_empty(self) -> None:
        """An empty marker resolves to the project directory itself, which always exists, so the
        platform would be detected in every project. It must be refused at construction."""
        with pytest.raises(ValueError):
            _row(markers=("",))

    def test_a_marker_path_must_stay_inside_the_project(self) -> None:
        """Detection looks a marker up under the project directory; an absolute marker is looked up
        wherever it points, so a platform would be detected from outside the project."""
        with pytest.raises(ValueError):
            _row(markers=("/etc",))


class TestLaneIds:
    def test_an_empty_lane_is_refused_rather_than_read_as_manual(self) -> None:
        with pytest.raises(ValueError, match="lane"):
            _row(lane="")
