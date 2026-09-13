# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``build_snapshot`` — the one impure module in the doctor package: exercised against a real,
temporary project tree rather than the live repository, so a change to THIS repo's own layout
never breaks these tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from narrativetrace.doctor import environment
from narrativetrace.doctor.environment import _resolve_package_info, build_snapshot


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestBuildSnapshot:
    def test_reads_the_root_pyproject(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml", "[project]\nname = 'demo'\n")
        snapshot = build_snapshot(str(tmp_path), {})
        assert snapshot.root_pyproject == {"project": {"name": "demo"}}

    def test_missing_pyproject_is_none(self, tmp_path: Path) -> None:
        snapshot = build_snapshot(str(tmp_path), {})
        assert snapshot.root_pyproject is None

    def test_malformed_pyproject_is_none(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml", "not [ valid toml")
        snapshot = build_snapshot(str(tmp_path), {})
        assert snapshot.root_pyproject is None

    def test_python_version_has_three_dotted_parts(self, tmp_path: Path) -> None:
        snapshot = build_snapshot(str(tmp_path), {})
        assert len(snapshot.python_version.split(".")) == 3

    def test_env_passes_through(self, tmp_path: Path) -> None:
        snapshot = build_snapshot(str(tmp_path), {"NARRATIVETRACE_OUTPUT": "true"})
        assert snapshot.env["NARRATIVETRACE_OUTPUT"] == "true"

    def test_source_files_bucketed_by_extension(self, tmp_path: Path) -> None:
        _write(tmp_path / "app.py", "print(1)")
        _write(tmp_path / "notes.txt", "irrelevant")
        snapshot = build_snapshot(str(tmp_path), {})
        assert "app.py" in snapshot.source_files
        assert "notes.txt" not in snapshot.source_files

    def test_output_directory_files_bucketed_separately(self, tmp_path: Path) -> None:
        _write(tmp_path / "narrative-traces" / "T" / "m.md", "trace")
        _write(tmp_path / "app.py", "print(1)")
        snapshot = build_snapshot(str(tmp_path), {})
        assert snapshot.output_files == {str(Path("narrative-traces", "T", "m.md")): "trace"}
        assert "app.py" in snapshot.source_files

    def test_approved_directory_files_bucketed_separately(self, tmp_path: Path) -> None:
        _write(tmp_path / "test-narratives" / "T" / "m.approved.nt", "scenario: s\n")
        snapshot = build_snapshot(str(tmp_path), {})
        assert list(snapshot.approved_dir_files) == [
            str(Path("test-narratives", "T", "m.approved.nt"))
        ]

    def test_configured_output_dir_name_is_honored(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml", "[tool.narrativetrace]\noutput_dir = 'built-traces'\n")
        _write(tmp_path / "built-traces" / "T" / "m.md", "trace")
        snapshot = build_snapshot(str(tmp_path), {})
        assert list(snapshot.output_files) == [str(Path("built-traces", "T", "m.md"))]

    def test_hidden_directories_are_excluded(self, tmp_path: Path) -> None:
        _write(tmp_path / ".git" / "config", "ignored")
        snapshot = build_snapshot(str(tmp_path), {})
        assert snapshot.source_files == {}

    def test_venv_directory_is_excluded(self, tmp_path: Path) -> None:
        _write(tmp_path / ".venv" / "lib" / "site.py", "ignored")
        snapshot = build_snapshot(str(tmp_path), {})
        assert snapshot.source_files == {}

    def test_narrativetrace_config_reflects_the_discovered_file(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml", "[tool.narrativetrace]\nlevel = 'DETAIL'\n")
        snapshot = build_snapshot(str(tmp_path), {})
        assert snapshot.narrativetrace_config == {"level": "DETAIL"}

    def test_no_config_file_gives_an_empty_config(self, tmp_path: Path) -> None:
        snapshot = build_snapshot(str(tmp_path), {})
        assert snapshot.narrativetrace_config == {}

    def test_installed_packages_includes_narrativetrace_itself(self, tmp_path: Path) -> None:
        snapshot = build_snapshot(str(tmp_path), {})
        assert "narrativetrace" in snapshot.installed_packages
        assert snapshot.installed_packages["narrativetrace"].requires_python is not None

    def test_pytest11_entry_points_includes_this_repos_own_plugin(self, tmp_path: Path) -> None:
        snapshot = build_snapshot(str(tmp_path), {})
        assert (
            snapshot.pytest11_entry_points.get("narrativetrace") == "narrativetrace_pytest.plugin"
        )

    def test_a_broken_symlink_reads_as_empty_content_not_a_crash(self, tmp_path: Path) -> None:
        target = tmp_path / "does-not-exist.py"
        link = tmp_path / "broken.py"
        link.symlink_to(target)
        snapshot = build_snapshot(str(tmp_path), {})
        assert snapshot.source_files == {"broken.py": ""}

    @pytest.mark.skipif(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        reason="root ignores directory permission bits, so this can't be exercised as root",
    )
    def test_an_unreadable_directory_is_skipped_not_a_crash(self, tmp_path: Path) -> None:
        blocked = tmp_path / "blocked"
        blocked.mkdir()
        _write(blocked / "app.py", "print(1)")
        _write(tmp_path / "app.py", "print(1)")
        os.chmod(blocked, 0o000)
        try:
            snapshot = build_snapshot(str(tmp_path), {})
        finally:
            # Restoring permissions on a locked-down tmp_path directory so pytest can clean it up
            # afterward -- not a real filesystem this permission mask reaches beyond the test.
            os.chmod(blocked, 0o755)  # nosec B103
        assert snapshot.source_files == {"app.py": "print(1)"}

    def test_the_file_bound_stops_the_walk_rather_than_hanging(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(environment, "_MAX_FILES", 1)
        _write(tmp_path / "a.py", "1")
        _write(tmp_path / "b.py", "2")
        snapshot = build_snapshot(str(tmp_path), {})
        assert len(snapshot.source_files) <= 1


class TestResolvePackageInfo:
    def test_none_for_a_distribution_that_is_not_installed(self) -> None:
        assert _resolve_package_info("definitely-not-a-real-distribution-xyz") is None

    def test_resolves_a_real_installed_distribution(self) -> None:
        info = _resolve_package_info("narrativetrace")
        assert info is not None
        assert info.name == "narrativetrace"
