# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`scripts/mutation_workers.py`: the worker-pool size every `poe mutate*` task runs with.

2026-09-17 Linux nightly finding F3 (family-wide): mutmut and Stryker size their worker pools
from the HOST's core count, so on a cgroup-quota'd container they oversubscribe — three
concurrent mutation runs each claimed all eight cores of an 8-core VM. The count now comes from
the container's own quota (`/sys/fs/cgroup/cpu.max`), or from `NT_MUTATION_WORKERS` when the
caller names it (the Pro nightly passes `NT_MUTATION_WORKERS=4`), and never from a bare host-core
count on a quota'd host.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from scripts import mutation_workers
from scripts.mutation_workers import (
    WORKERS_ENV_VAR,
    mutmut_command,
    resolve_worker_count,
    worker_count,
)


class TestWorkerCountFromTheEnvironment:
    def test_an_explicit_setting_wins_over_every_derivation(self) -> None:
        assert worker_count({"NT_MUTATION_WORKERS": "4"}, "max 100000\n", host_cpu_count=8) == 4

    def test_a_non_integer_setting_is_rejected_rather_than_silently_ignored(self) -> None:
        with pytest.raises(ValueError, match=r"\ANT_MUTATION_WORKERS must be a positive integer"):
            worker_count({"NT_MUTATION_WORKERS": "four"}, None, host_cpu_count=8)

    def test_a_zero_or_negative_setting_is_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"\ANT_MUTATION_WORKERS must be a positive integer"):
            worker_count({"NT_MUTATION_WORKERS": "0"}, None, host_cpu_count=8)

    def test_a_blank_setting_falls_through_to_the_derivation(self) -> None:
        """An empty env var is how a shell spells "unset" by accident; it must not raise, and it
        must not be read as a worker count either."""
        assert worker_count({"NT_MUTATION_WORKERS": ""}, "400000 100000\n", host_cpu_count=8) == 4


class TestWorkerCountFromTheCgroupQuota:
    def test_a_whole_number_quota_is_that_many_workers(self) -> None:
        """The finding's own case: a 4-CPU quota on an 8-core host is FOUR workers, never eight."""
        assert worker_count({}, "400000 100000\n", host_cpu_count=8) == 4

    def test_a_fractional_quota_rounds_up_so_the_pool_is_never_empty(self) -> None:
        assert worker_count({}, "450000 100000\n", host_cpu_count=8) == 5

    def test_a_sub_single_cpu_quota_still_yields_one_worker(self) -> None:
        assert worker_count({}, "50000 100000\n", host_cpu_count=8) == 1

    def test_an_unlimited_quota_falls_back_to_the_runtime_cpu_count(self) -> None:
        assert worker_count({}, "max 100000\n", host_cpu_count=8) == 8

    def test_no_cgroup_file_falls_back_to_the_runtime_cpu_count(self) -> None:
        assert worker_count({}, None, host_cpu_count=8) == 8

    def test_an_unparsable_cgroup_file_falls_back_to_the_runtime_cpu_count(self) -> None:
        assert worker_count({}, "garbage\n", host_cpu_count=8) == 8

    def test_a_zero_period_is_not_a_division_by_zero(self) -> None:
        assert worker_count({}, "400000 0\n", host_cpu_count=8) == 8

    def test_an_unknown_host_cpu_count_still_yields_one_worker(self) -> None:
        """`os.cpu_count()` returns None on platforms that cannot tell."""
        assert worker_count({}, None, host_cpu_count=None) == 1


class TestTheCommandTheTasksRun:
    def test_the_derived_count_is_passed_as_mutmut_s_max_children_flag(self) -> None:
        assert mutmut_command(4) == [sys.executable, "-m", "mutmut", "run", "--max-children", "4"]

    def test_extra_arguments_follow_the_flag_so_a_run_can_be_scoped(self) -> None:
        assert mutmut_command(2, ["narrativetrace.ids.*"]) == [
            sys.executable,
            "-m",
            "mutmut",
            "run",
            "--max-children",
            "2",
            "narrativetrace.ids.*",
        ]


class TestResolvingAgainstTheRealFilesystem:
    """`worker_count` is pure; these cover the two reads that feed it, so a container's quota
    file is proven to be read rather than merely parsed (release rule 2)."""

    def test_the_cgroup_quota_file_is_read_when_it_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cpu_max = tmp_path / "cpu.max"
        cpu_max.write_text("300000 100000\n", encoding="utf-8")
        monkeypatch.setattr(mutation_workers, "CGROUP_CPU_MAX", cpu_max)
        monkeypatch.delenv(WORKERS_ENV_VAR, raising=False)
        assert resolve_worker_count() == 3

    def test_an_absent_cgroup_quota_file_is_not_an_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """macOS, a bare host and cgroup v1 all have no `cpu.max` — the derivation degrades to
        the runtime CPU count instead of raising."""
        monkeypatch.setattr(mutation_workers, "CGROUP_CPU_MAX", tmp_path / "absent")
        monkeypatch.delenv(WORKERS_ENV_VAR, raising=False)
        assert resolve_worker_count() >= 1


class TestTheLauncher:
    def test_main_announces_the_count_runs_mutmut_guarded_and_returns_its_exit_code(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """mutmut runs wrapped in `run_guarded`, never a bare `subprocess.run` -- a test that
        rewrites a tracked file under mutation must fail the run, not exit clean with the tree
        dirtied."""
        recorded: list[list[str]] = []

        def _fake_run_guarded(argv: list[str]) -> int:
            recorded.append(argv)
            return 7

        monkeypatch.setattr(mutation_workers, "run_guarded", _fake_run_guarded)
        monkeypatch.setenv(WORKERS_ENV_VAR, "3")
        assert mutation_workers.main(["narrativetrace.ids.*"]) == 7
        assert recorded == [mutmut_command(3, ["narrativetrace.ids.*"])]
        assert (
            f"mutation-workers: running mutmut with --max-children 3 (from {WORKERS_ENV_VAR})"
            in capsys.readouterr().out
        )
