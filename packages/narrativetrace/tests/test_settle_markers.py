# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for `scripts/settle_markers.py` (`scripts/settle-markers.sh <version>` — the post-publish
marker settle; see that module's own docstring for the full design note).

`main()`'s stdout/exit-code glue is exercised for real by actually running the settle right after
a release (the "after the tag publish" step in this repository's own release procedure); these
tests drive
`discover_marker_files`, `settle_version` and `refusal_reason` directly against synthetic
`tmp_path` trees, the same split `test_llms_banner.py` and `test_translation_check.py` use — plus
one `main()` test with the registry check monkeypatched out, proving the "nothing to settle is a
mistake, not a success" exit code without a real network call.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.settle_markers import discover_marker_files, main, refusal_reason, settle_version
from scripts.translation_check import git_blob_hash


def _header(source: str, blob: str) -> str:
    return f"<!-- source: {source} blob {blob} | translated: 2026-09-03 -->"


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _fixture_repo(root: Path) -> Path:
    """One doc carrying a marker for the version under test AND a marker for a later version,
    plus a translated mirror of that same doc carrying its own copy of the settling marker — the
    exact shape the settle step has to handle: rewrite the settling marker wherever it sits, leave
    the later-version marker alone, and restamp the mirror's header once its named source's bytes
    change as a result."""
    guide = _write(
        root,
        "documentation/guide.md",
        "# Guide\n\nOne behaviour *(since 0.1.2, unreleased)*.\n\n"
        "A future one *(since 0.2.0, unreleased)*.\n",
    )
    original_hash = git_blob_hash(guide.read_bytes())[:12]
    _write(
        root,
        "documentation/es/guide.md",
        _header("documentation/guide.md", original_hash)
        + "\n# Guía\n\nUn comportamiento *(since 0.1.2, unreleased)*.\n",
    )
    return root


class TestSettleVersion:
    def test_settles_only_the_cited_version(self, tmp_path: Path) -> None:
        _fixture_repo(tmp_path)

        settle_version(tmp_path, "0.1.2")

        guide_text = (tmp_path / "documentation" / "guide.md").read_text(encoding="utf-8")
        assert "*(since 0.1.2)*" in guide_text
        assert "since 0.1.2, unreleased" not in guide_text

    def test_a_later_versions_marker_survives(self, tmp_path: Path) -> None:
        _fixture_repo(tmp_path)

        settle_version(tmp_path, "0.1.2")

        guide_text = (tmp_path / "documentation" / "guide.md").read_text(encoding="utf-8")
        assert "*(since 0.2.0, unreleased)*" in guide_text

    def test_the_mirrors_own_copy_of_the_marker_settles_too(self, tmp_path: Path) -> None:
        _fixture_repo(tmp_path)

        settle_version(tmp_path, "0.1.2")

        mirror_text = (tmp_path / "documentation" / "es" / "guide.md").read_text(encoding="utf-8")
        assert "*(since 0.1.2)*" in mirror_text
        assert "since 0.1.2, unreleased" not in mirror_text

    def test_the_mirror_header_restamps_to_the_new_source_hash(self, tmp_path: Path) -> None:
        _fixture_repo(tmp_path)

        settle_version(tmp_path, "0.1.2")

        new_hash = git_blob_hash((tmp_path / "documentation" / "guide.md").read_bytes())[:12]
        mirror_first_line = (
            (tmp_path / "documentation" / "es" / "guide.md")
            .read_text(encoding="utf-8")
            .splitlines()[0]
        )
        assert f"source: documentation/guide.md blob {new_hash}" in mirror_first_line

    def test_the_restamp_never_touches_the_translated_date(self, tmp_path: Path) -> None:
        _fixture_repo(tmp_path)

        settle_version(tmp_path, "0.1.2")

        mirror_first_line = (
            (tmp_path / "documentation" / "es" / "guide.md")
            .read_text(encoding="utf-8")
            .splitlines()[0]
        )
        assert "translated: 2026-09-03" in mirror_first_line

    def test_reports_the_marker_count_and_touched_files(self, tmp_path: Path) -> None:
        _fixture_repo(tmp_path)

        result = settle_version(tmp_path, "0.1.2")

        assert result.marker_count == 2
        assert "documentation/guide.md" in result.rewritten_files
        assert "documentation/es/guide.md" in result.rewritten_files
        assert result.restamped_files == ["documentation/es/guide.md"]

    def test_a_version_cited_nowhere_settles_nothing(self, tmp_path: Path) -> None:
        _fixture_repo(tmp_path)

        result = settle_version(tmp_path, "9.9.9")

        assert result.marker_count == 0
        assert result.rewritten_files == []
        assert result.restamped_files == []

    def test_running_twice_rewrites_nothing_the_second_time(self, tmp_path: Path) -> None:
        _fixture_repo(tmp_path)
        settle_version(tmp_path, "0.1.2")

        second = settle_version(tmp_path, "0.1.2")

        assert second.marker_count == 0

    def test_a_page_changed_only_by_the_regenerate_hook_still_restamps_its_mirror(
        self, tmp_path: Path
    ) -> None:
        """The regression this test pins: a real release settled markers and restamped every
        mirror whose SOURCE carried a marker, but a translated mirror of a *different* page --
        one with no marker at all, mutated only by the banner/snippet regeneration step that
        runs as part of the same settle -- was left pointing at the page's stale
        pre-regeneration hash. `regenerate` stands in for that real step
        (`llms_banner.sync_banner` in production): this fixture's fake mutates an English page
        that carries no marker at all, and the settle must still pick up the resulting hash
        change and restamp that page's mirror."""
        root = _fixture_repo(tmp_path)
        other = _write(root, "documentation/other.md", "# Other\n\nNo marker here.\n")
        original_other_hash = git_blob_hash(other.read_bytes())[:12]
        _write(
            root,
            "documentation/es/other.md",
            _header("documentation/other.md", original_other_hash) + "\n# Otro\n\nSin marcador.\n",
        )

        def regenerate(repo_root: Path) -> None:
            target = repo_root / "documentation" / "other.md"
            target.write_text(
                target.read_text(encoding="utf-8") + "\nRegenerated line.\n", encoding="utf-8"
            )

        settle_version(tmp_path, "0.1.2", regenerate=regenerate)

        new_hash = git_blob_hash((tmp_path / "documentation" / "other.md").read_bytes())[:12]
        assert new_hash != original_other_hash
        mirror_first_line = (
            (tmp_path / "documentation" / "es" / "other.md")
            .read_text(encoding="utf-8")
            .splitlines()[0]
        )
        assert f"source: documentation/other.md blob {new_hash}" in mirror_first_line


class TestDiscoverMarkerFiles:
    def test_never_touches_a_file_outside_the_documentation_and_readme_scope(
        self, tmp_path: Path
    ) -> None:
        _fixture_repo(tmp_path)
        outside = _write(
            tmp_path,
            "packages/narrativetrace/tests/fixtures/marker_shaped.md",
            "*(since 0.1.2, unreleased)*",
        )

        found = {p.resolve() for p in discover_marker_files(tmp_path)}

        assert outside.resolve() not in found

    def test_the_root_readme_and_its_translated_mirror_are_in_scope(self, tmp_path: Path) -> None:
        readme = _write(tmp_path, "README.md", "# Project\n\n*(since 0.1.2, unreleased)*\n")
        original_hash = git_blob_hash(readme.read_bytes())[:12]
        _write(tmp_path, "LEAME.md", _header("README.md", original_hash) + "\n# Proyecto\n")

        found = {p.name for p in discover_marker_files(tmp_path)}

        assert "README.md" in found
        assert "LEAME.md" in found


class TestRefusalReason:
    def test_none_when_the_registry_already_reports_this_version(self, tmp_path: Path) -> None:
        reason = refusal_reason(tmp_path, "0.1.2", fetch=lambda name: "0.1.2")

        assert reason is None

    def test_refuses_a_version_the_registry_does_not_report_yet(self, tmp_path: Path) -> None:
        reason = refusal_reason(tmp_path, "0.1.2", fetch=lambda name: "0.1.1")

        assert reason is not None
        assert "0.1.1" in reason

    def test_refuses_when_offline_with_no_fresh_cache(self, tmp_path: Path) -> None:
        reason = refusal_reason(tmp_path, "0.1.2", fetch=lambda name: None)

        assert reason is not None
        assert "offline" in reason


class TestMainExitCode:
    def test_nothing_to_settle_is_a_mistake_not_a_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _fixture_repo(tmp_path)
        monkeypatch.setattr("scripts.settle_markers.REPO_ROOT", tmp_path)
        monkeypatch.setattr("scripts.settle_markers.refusal_reason", lambda *a, **k: None)

        exit_code = main(["9.9.9"])

        assert exit_code == 1

    def test_a_registry_refusal_exits_red_before_touching_any_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _fixture_repo(tmp_path)
        monkeypatch.setattr("scripts.settle_markers.REPO_ROOT", tmp_path)
        monkeypatch.setattr(
            "scripts.settle_markers.refusal_reason", lambda *a, **k: "not on the registry yet"
        )

        exit_code = main(["0.1.2"])

        assert exit_code == 1
        guide_text = (tmp_path / "documentation" / "guide.md").read_text(encoding="utf-8")
        assert "since 0.1.2, unreleased" in guide_text
