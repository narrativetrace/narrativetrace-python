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

import resource
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import mutation_workers
from scripts.mutation_workers import (
    MEMORY_ENV_VAR,
    MEMORY_FLOOR_BYTES,
    WORKERS_ENV_VAR,
    memory_limit_bytes,
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


def _platform_enforces_data_limit() -> str | None:
    """``None`` when this platform lets a process LOWER its ``RLIMIT_DATA``, else the refusal.

    A real probe, not a platform name, and the real operation: macOS accepts re-setting the
    current (unlimited) value but refuses every lowering with ``EINVAL``, so only an attempt to
    lower tells the truth. It runs in a child so the test process keeps its own limits.
    """
    code = (
        "import resource\n"
        "resource.setrlimit(resource.RLIMIT_DATA, (200 * 1024 * 1024, 200 * 1024 * 1024))\n"
    )
    done = subprocess.run(  # nosec B603 - this interpreter, a fixed snippet, no shell
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if done.returncode == 0:
        return None
    stderr = done.stderr.strip()
    return stderr.splitlines()[-1] if stderr else f"exit {done.returncode}"


class TestPerProcessMemoryLimit:
    """B-218 (2026-10-28 nightly): a runaway mutant (`i += 1` -> `i = 1` in `line_diff._render`)
    grew until the container's cgroup OOM killer ended the run, taking a bystander (the mutmut
    parent) with it. Every mutmut process gets a limit below its share of `memory.max`, so the
    runaway dies of `MemoryError` alone."""

    def test_the_limit_is_the_cgroup_cap_shared_by_the_workers_and_the_parent(self) -> None:
        assert memory_limit_bytes({}, "8589934592\n", workers=3) == 8589934592 // 4

    def test_a_share_below_the_floor_is_raised_to_the_floor(self) -> None:
        assert memory_limit_bytes({}, "1572864000\n", workers=4) == MEMORY_FLOOR_BYTES

    @pytest.mark.parametrize("cgroup_memory_max", ["max\n", None, "garbage\n", "0\n", "-5\n", ""])
    def test_no_usable_cgroup_cap_means_no_limit(self, cgroup_memory_max: str | None) -> None:
        assert memory_limit_bytes({}, cgroup_memory_max, workers=4) is None

    def test_the_override_in_megabytes_wins_over_the_cgroup_cap(self) -> None:
        env = {MEMORY_ENV_VAR: "700"}
        assert memory_limit_bytes(env, "1572864000\n", workers=4) == 700 * 1024 * 1024

    def test_the_override_applies_even_without_a_cgroup_cap(self) -> None:
        assert memory_limit_bytes({MEMORY_ENV_VAR: "700"}, None, workers=4) == 700 * 1024 * 1024

    def test_a_blank_override_falls_through_to_the_cgroup_cap(self) -> None:
        assert memory_limit_bytes({MEMORY_ENV_VAR: " "}, "8589934592\n", workers=3) == 2147483648

    @pytest.mark.parametrize("raw", ["lots", "0", "-1", "1.5"])
    def test_a_malformed_override_is_an_error_never_a_silent_fallback(self, raw: str) -> None:
        with pytest.raises(ValueError, match=r"\ANT_MUTATION_MEMORY_MB must be a positive integer"):
            memory_limit_bytes({MEMORY_ENV_VAR: raw}, "1572864000\n", workers=4)

    @pytest.mark.parametrize("refusal", [ValueError, OSError])
    def test_a_platform_that_refuses_the_limit_gets_one_diagnostic_never_a_crash(
        self,
        refusal: type[Exception],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def refuse(which: int, limits: tuple[int, int]) -> None:
            raise refusal("current limit exceeds maximum limit")

        monkeypatch.setattr(resource, "setrlimit", refuse)
        mutation_workers.apply_memory_limit(200 * 1024 * 1024)
        assert capsys.readouterr().out == (
            "mutation-workers: memory limit 200 MiB not enforceable on this platform "
            "(current limit exceeds maximum limit), running unbounded\n"
        )

    def test_the_limit_really_stops_a_runaway_allocation_with_memory_error(self) -> None:
        """The setter is proven against a real process: past the limit the allocation raises
        `MemoryError` inside that process instead of growing until something else kills it."""
        reason = _platform_enforces_data_limit()
        if reason is not None:
            pytest.skip(f"this platform refuses RLIMIT_DATA: {reason}")
        root = Path(mutation_workers.__file__).resolve().parent.parent
        code = (
            "from scripts.mutation_workers import apply_memory_limit\n"
            "apply_memory_limit(200 * 1024 * 1024)\n"
            "try:\n"
            "    bytearray(3 * 1024 * 1024 * 1024)\n"
            "except MemoryError:\n"
            "    print('bounded')\n"
        )
        done = subprocess.run(  # nosec B603 - this interpreter, a fixed snippet, no shell
            [sys.executable, "-c", code],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert (done.returncode, done.stdout.strip()) == (0, "bounded")

    def test_no_limit_leaves_the_process_unbounded(self) -> None:
        root = Path(mutation_workers.__file__).resolve().parent.parent
        code = (
            "import resource\n"
            "from scripts.mutation_workers import apply_memory_limit\n"
            "before = resource.getrlimit(resource.RLIMIT_DATA)\n"
            "apply_memory_limit(None)\n"
            "print(before == resource.getrlimit(resource.RLIMIT_DATA))\n"
        )
        done = subprocess.run(  # nosec B603 - this interpreter, a fixed snippet, no shell
            [sys.executable, "-c", code],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert done.stdout.strip() == "True"


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

    def test_the_cgroup_memory_file_is_read_when_it_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        memory_max = tmp_path / "memory.max"
        memory_max.write_text("1572864000\n", encoding="utf-8")
        monkeypatch.setattr(mutation_workers, "CGROUP_MEMORY_MAX", memory_max)
        assert mutation_workers.resolve_memory_limit({}, workers=4) == MEMORY_FLOOR_BYTES

    def test_an_absent_cgroup_memory_file_means_no_limit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mutation_workers, "CGROUP_MEMORY_MAX", tmp_path / "absent")
        assert mutation_workers.resolve_memory_limit({}, workers=4) is None


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

    def test_main_applies_the_memory_limit_before_launching_mutmut(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The limit is set in the launcher so every process mutmut forks inherits it; applied
        after the launch it would bound nothing."""
        events: list[object] = []
        memory_max = tmp_path / "memory.max"
        memory_max.write_text("1572864000\n", encoding="utf-8")
        monkeypatch.setattr(mutation_workers, "CGROUP_MEMORY_MAX", memory_max)

        def _launch(argv: list[str]) -> int:
            events.append("launch")
            return 0

        monkeypatch.setattr(mutation_workers, "run_guarded", _launch)
        monkeypatch.setenv(WORKERS_ENV_VAR, "4")
        monkeypatch.delenv(MEMORY_ENV_VAR, raising=False)

        def _record_limit(limit: int | None) -> None:
            events.append(limit)

        assert mutation_workers.main([], limit_setter=_record_limit) == 0
        assert events == [MEMORY_FLOOR_BYTES, "launch"]

    def test_main_passes_no_limit_when_the_container_has_no_cap(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        events: list[object] = []
        monkeypatch.setattr(mutation_workers, "CGROUP_MEMORY_MAX", tmp_path / "absent")
        monkeypatch.setattr(mutation_workers, "run_guarded", lambda argv: 0)
        monkeypatch.setenv(WORKERS_ENV_VAR, "4")
        monkeypatch.delenv(MEMORY_ENV_VAR, raising=False)

        def _record_limit(limit: int | None) -> None:
            events.append(limit)

        mutation_workers.main([], limit_setter=_record_limit)
        assert events == [None]

    def test_main_rejects_a_malformed_memory_override_before_launching(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        launched: list[object] = []
        monkeypatch.setattr(mutation_workers, "run_guarded", launched.append)
        monkeypatch.setenv(WORKERS_ENV_VAR, "4")
        monkeypatch.setenv(MEMORY_ENV_VAR, "lots")
        with pytest.raises(ValueError, match=r"\ANT_MUTATION_MEMORY_MB"):
            mutation_workers.main([], limit_setter=lambda limit: None)
        assert launched == []
