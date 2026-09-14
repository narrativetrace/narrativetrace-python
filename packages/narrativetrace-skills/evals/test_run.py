# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest
import run
from quota import QuotaSpendRow


class RecordingSpawn:
    """A fake ``Spawner``: records every ``(argv, cwd)`` call, no real subprocess. Can be told to
    raise for the grader step (``argv[0] == "sh"``) or the agent step (anything else), so a test
    drives pass/fail/crash without a real CLI."""

    def __init__(
        self,
        *,
        agent_raises: Exception | None = None,
        grader_raises: Exception | None = None,
    ) -> None:
        self.calls: list[tuple[list[str], Path]] = []
        self._agent_raises = agent_raises
        self._grader_raises = grader_raises

    def __call__(self, argv: Sequence[str], cwd: Path) -> None:
        argv_list = list(argv)
        self.calls.append((argv_list, cwd))
        is_grader_call = argv_list[:1] == ["sh"]
        if is_grader_call and self._grader_raises is not None:
            raise self._grader_raises
        if not is_grader_call and self._agent_raises is not None:
            raise self._agent_raises

    @property
    def agent_calls(self) -> list[tuple[list[str], Path]]:
        return [call for call in self.calls if call[0][:1] != ["sh"]]

    @property
    def grader_calls(self) -> list[tuple[list[str], Path]]:
        return [call for call in self.calls if call[0][:1] == ["sh"]]


@pytest.fixture
def synthetic_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Points run.py's module-relative path constants at a throwaway repo layout so the trial-flow
    tests never touch this repo's own fixtures or case content. Deliberate: under
    ``mutmut``, the mutated copy of ``run.py`` lives at a different depth (``mutants/evals/``),
    which changes what ``_REPO_ROOT``/``_EVALS_DIR`` resolve to — any test that depended on the
    real repo tree via those constants would fail for every mutant, not just a real regression."""
    repo_root = tmp_path / "repo"
    evals_dir = repo_root / "packages" / "narrativetrace-skills" / "evals"
    evals_dir.mkdir(parents=True)
    monkeypatch.setattr(run, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(run, "_EVALS_DIR", evals_dir)
    return repo_root


def _add_case(
    repo_root: Path,
    skill: str,
    case_name: str,
    *,
    prompt: str = "do the thing",
    fixture: str = "fixtures/demo",
) -> None:
    """Populates a case directory (prompt + graders/) under ``synthetic_repo``'s evals tree, and a
    fixture directory under its repo root, mirroring the real layout closely enough for
    ``run_trials``/``_run_one_trial`` to exercise the whole flow."""
    case_dir = repo_root / "packages" / "narrativetrace-skills" / "evals" / skill / case_name
    (case_dir / "graders").mkdir(parents=True)
    (case_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    (case_dir / "case.json").write_text(json.dumps({"fixture": fixture}), encoding="utf-8")
    fixture_src = repo_root / fixture
    fixture_src.mkdir(parents=True)
    (fixture_src / "marker.txt").write_text("fixture-content", encoding="utf-8")


def _run_args(**overrides: object) -> run.RunArgs:
    defaults: dict[str, object] = {
        "skill": "demo-skill",
        "case_name": "happy-path",
        "platform": "claude",
        "model": "haiku",
        "agent_command": 'echo "{prompt}"',
        "trials": 1,
    }
    defaults.update(overrides)
    return run.RunArgs(**defaults)  # type: ignore[arg-type]


def _quota_markdown(weekly_allowance: int, spend_rows: str = "") -> str:
    return (
        "# quota\n\n## Allowance\n\n| platform | plan tier | weekly allowance |\n|---|---|---|\n"
        f"| codex | basic | {weekly_allowance} |\n\n"
        "## Spend log\n\n| date | platform | skill | case | week |\n|---|---|---|---|---|\n"
        f"{spend_rows}"
    )


class TestDefaultSpawner:
    def test_runs_a_successful_command(self, tmp_path: Path) -> None:
        run.default_spawner(["true"], tmp_path)  # must not raise

    def test_raises_on_a_nonzero_exit(self, tmp_path: Path) -> None:
        with pytest.raises(subprocess.CalledProcessError):
            run.default_spawner(["false"], tmp_path)

    def test_argv_elements_are_not_shell_parsed(self, tmp_path: Path) -> None:
        # If this ran through a shell, "&&" would separate two commands and create two files;
        # passed as argv it is one filename, proving no shell ever re-parses an argv element.
        run.default_spawner(["touch", "a && touch pwned.txt"], tmp_path)
        assert [p.name for p in tmp_path.iterdir()] == ["a && touch pwned.txt"]


class TestRunDeps:
    def test_production_defaults(self) -> None:
        deps = run.RunDeps()
        assert deps.spawn is run.default_spawner
        assert deps.clock == date.today  # bound builtin methods aren't `is`-identical per access
        assert deps.ledger_path == run._LEDGER_PATH
        assert deps.quota_path == run._QUOTA_PATH


class TestParseArgs:
    def test_parses_required_flags_with_defaults(self) -> None:
        args = run._parse_args(
            ["--skill", "s", "--case", "c", "--platform", "claude", "--model", "haiku"]
        )
        assert args == run.RunArgs(
            skill="s",
            case_name="c",
            platform="claude",
            model="haiku",
            agent_command=None,
            trials=1,
        )

    def test_parses_agent_command_and_trials(self) -> None:
        args = run._parse_args(
            [
                "--skill",
                "s",
                "--case",
                "c",
                "--platform",
                "codex",
                "--model",
                "mini",
                "--agent-command",
                "codex {prompt}",
                "--trials",
                "3",
            ]
        )
        assert args.agent_command == "codex {prompt}"
        assert args.trials == 3

    def test_rejects_an_unknown_platform(self) -> None:
        with pytest.raises(SystemExit):
            run._parse_args(
                ["--skill", "s", "--case", "c", "--platform", "chatgpt", "--model", "x"]
            )


class TestCaseFixture:
    def test_falls_back_to_the_canonical_fixture_when_no_manifest(
        self, synthetic_repo: Path
    ) -> None:
        assert run._case_fixture("no-such-skill", "no-such-case") == "examples/sixty_seconds"

    def test_reads_the_fixture_from_case_json_when_present(self, synthetic_repo: Path) -> None:
        case_dir = run._EVALS_DIR / "skill" / "case"
        case_dir.mkdir(parents=True)
        (case_dir / "case.json").write_text('{"fixture": "fixtures/custom"}', encoding="utf-8")
        assert run._case_fixture("skill", "case") == "fixtures/custom"


class TestScaffoldFixture:
    def test_copies_from_the_repo_root_constant_not_a_relative_path(
        self, synthetic_repo: Path
    ) -> None:
        """Regression pin for defect #1 in the TypeScript reference (a case/fixture path resolved
        relative to the caller's cwd): ``_scaffold_fixture`` must resolve solely from the
        ``_REPO_ROOT`` constant (itself derived from ``__file__``, never from cwd) -- proven here
        by pointing that constant at a throwaway repo the real process cwd has no relation to, and
        confirming the copy still finds it."""
        fixture_src = synthetic_repo / "fixtures" / "sample"
        fixture_src.mkdir(parents=True)
        (fixture_src / "marker.txt").write_text("hello", encoding="utf-8")

        scratch = run._scaffold_fixture("fixtures/sample")
        try:
            assert (scratch / "marker.txt").read_text(encoding="utf-8") == "hello"
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


class TestTokenizeAgentCommand:
    def test_substitutes_the_prompt_as_a_single_token(self) -> None:
        argv = run._tokenize_agent_command('claude -p "{prompt}" --model haiku', "hello world")
        assert argv == ["claude", "-p", "hello world", "--model", "haiku"]

    def test_prompt_with_backticks_and_command_substitution_is_inert(self) -> None:
        hostile = "say `whoami` and $(rm -rf /)"
        argv = run._tokenize_agent_command('claude -p "{prompt}"', hostile)
        assert argv == ["claude", "-p", hostile]

    def test_prompt_with_quotes_and_a_newline_arrives_verbatim(self) -> None:
        hostile = 'a "quoted" phrase\nand a second line'
        argv = run._tokenize_agent_command('claude -p "{prompt}"', hostile)
        assert argv[-1] == hostile

    def test_prompt_embedded_within_a_larger_token_still_substitutes(self) -> None:
        argv = run._tokenize_agent_command("tool --input={prompt}", "value")
        assert argv == ["tool", "--input=value"]


class TestRunGrader:
    def test_pass_when_spawn_succeeds(self, tmp_path: Path) -> None:
        case_dir = tmp_path / "case"
        spy = RecordingSpawn()
        assert run._run_grader(case_dir, tmp_path, spy) == "pass"
        assert spy.calls == [(["sh", str(case_dir / "graders" / "verify.sh")], tmp_path)]

    def test_fail_when_spawn_raises_called_process_error(self, tmp_path: Path) -> None:
        case_dir = tmp_path / "case"
        spy = RecordingSpawn(grader_raises=subprocess.CalledProcessError(1, ["sh"]))
        assert run._run_grader(case_dir, tmp_path, spy) == "fail"

    def test_fail_when_spawn_raises_os_error(self, tmp_path: Path) -> None:
        case_dir = tmp_path / "case"
        spy = RecordingSpawn(grader_raises=OSError("no such file"))
        assert run._run_grader(case_dir, tmp_path, spy) == "fail"


class TestAppendLedgerRow:
    def test_appends_one_json_line(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "runs.jsonl"
        run._append_ledger_row(ledger_path, {"a": 1})
        run._append_ledger_row(ledger_path, {"a": 2})
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
        assert lines == ['{"a": 1}', '{"a": 2}']


class TestAssertQuotaAvailable:
    def test_allows_when_under_the_weekly_allowance(self, tmp_path: Path) -> None:
        quota_path = tmp_path / "quota.md"
        quota_path.write_text(_quota_markdown(4), encoding="utf-8")
        run._assert_quota_available(quota_path, "codex", [], today=date(2026, 9, 7))

    def test_refuses_once_the_weekly_allowance_is_spent(self, tmp_path: Path) -> None:
        quota_path = tmp_path / "quota.md"
        spend = "| 2026-09-07 | codex | s | c | 2026-W37 |\n"
        quota_path.write_text(_quota_markdown(1, spend), encoding="utf-8")
        with pytest.raises(RuntimeError, match="no override"):
            run._assert_quota_available(quota_path, "codex", [], today=date(2026, 9, 7))

    def test_counts_this_sessions_own_spend_too(self, tmp_path: Path) -> None:
        quota_path = tmp_path / "quota.md"
        quota_path.write_text(_quota_markdown(1), encoding="utf-8")
        session_spend = [
            QuotaSpendRow(date="x", platform="codex", skill="s", case_name="c", week="2026-W37")
        ]
        with pytest.raises(RuntimeError):
            run._assert_quota_available(quota_path, "codex", session_spend, today=date(2026, 9, 7))

    def test_a_previous_iso_week_boundary_does_not_count_against_the_new_week(
        self, tmp_path: Path
    ) -> None:
        quota_path = tmp_path / "quota.md"
        # 2026-09-06 is the last day of ISO week 36; 2026-09-07 is the first day of week 37.
        spend = "| 2026-09-06 | codex | s | c | 2026-W36 |\n"
        quota_path.write_text(_quota_markdown(1, spend), encoding="utf-8")
        run._assert_quota_available(quota_path, "codex", [], today=date(2026, 9, 7))


class TestRecordSporadicSpend:
    def test_appends_a_row_dated_by_the_injected_clock(self, tmp_path: Path) -> None:
        quota_path = tmp_path / "quota.md"
        quota_path.write_text(_quota_markdown(4), encoding="utf-8")
        row = run._record_sporadic_spend(
            quota_path, _run_args(platform="codex"), today=date(2026, 9, 7)
        )
        assert row == QuotaSpendRow(
            date="2026-09-07",
            platform="codex",
            skill="demo-skill",
            case_name="happy-path",
            week="2026-W37",
        )
        assert "| 2026-09-07 | codex | demo-skill | happy-path | 2026-W37 |" in (
            quota_path.read_text(encoding="utf-8")
        )


class TestRunOneTrial:
    def test_pass_appends_a_pass_ledger_row(self, synthetic_repo: Path) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        ledger_path = synthetic_repo / "runs.jsonl"
        spy = RecordingSpawn()
        deps = run.RunDeps(spawn=spy, clock=lambda: date(2026, 9, 13), ledger_path=ledger_path)
        case_dir = run._EVALS_DIR / "demo-skill" / "happy-path"

        run._run_one_trial(_run_args(), case_dir, "the prompt", 1, deps)

        row = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert row["result"] == "pass"
        assert row["date"] == "2026-09-13"
        assert row["skill"] == "demo-skill"
        assert row["trial"] == 1

    def test_fail_when_the_grader_fails(self, synthetic_repo: Path) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        ledger_path = synthetic_repo / "runs.jsonl"
        spy = RecordingSpawn(grader_raises=subprocess.CalledProcessError(1, ["sh"]))
        deps = run.RunDeps(spawn=spy, clock=lambda: date(2026, 9, 13), ledger_path=ledger_path)
        case_dir = run._EVALS_DIR / "demo-skill" / "happy-path"

        run._run_one_trial(_run_args(), case_dir, "the prompt", 1, deps)

        row = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert row["result"] == "fail"

    def test_crash_when_the_agent_raises_propagates_and_skips_the_ledger(
        self, synthetic_repo: Path
    ) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        ledger_path = synthetic_repo / "runs.jsonl"
        spy = RecordingSpawn(agent_raises=subprocess.CalledProcessError(1, ["claude"]))
        deps = run.RunDeps(spawn=spy, clock=lambda: date(2026, 9, 13), ledger_path=ledger_path)
        case_dir = run._EVALS_DIR / "demo-skill" / "happy-path"

        with pytest.raises(subprocess.CalledProcessError):
            run._run_one_trial(_run_args(), case_dir, "the prompt", 1, deps)

        assert not ledger_path.exists()
        # the grader must never run once the agent step has crashed
        assert spy.grader_calls == []
        scratch = spy.agent_calls[0][1]
        assert not scratch.exists()  # cleaned up by the finally block even on crash

    def test_prompt_reaches_the_agent_as_a_single_verbatim_argv_element(
        self, synthetic_repo: Path
    ) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        ledger_path = synthetic_repo / "runs.jsonl"
        spy = RecordingSpawn()
        deps = run.RunDeps(spawn=spy, clock=lambda: date(2026, 9, 13), ledger_path=ledger_path)
        case_dir = run._EVALS_DIR / "demo-skill" / "happy-path"
        hostile_prompt = 'say `whoami` and $(rm -rf /) plus "quotes"\nand a newline'

        run._run_one_trial(
            _run_args(agent_command='echo "{prompt}"'), case_dir, hostile_prompt, 1, deps
        )

        argv, _ = spy.agent_calls[0]
        assert argv == ["echo", hostile_prompt]

    def test_skips_the_agent_step_when_no_agent_command_resolves(
        self,
        synthetic_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        monkeypatch.setattr(run, "preset_agent_command", lambda *_a, **_k: "")
        ledger_path = synthetic_repo / "runs.jsonl"
        spy = RecordingSpawn()
        deps = run.RunDeps(spawn=spy, clock=lambda: date(2026, 9, 13), ledger_path=ledger_path)
        case_dir = run._EVALS_DIR / "demo-skill" / "happy-path"

        run._run_one_trial(_run_args(agent_command=None), case_dir, "the prompt", 1, deps)

        assert spy.agent_calls == []
        assert spy.grader_calls != []
        assert "skipping the agent step" in capsys.readouterr().out


class TestRunTrials:
    def test_claude_is_exempt_from_tier_and_quota_checks(
        self, synthetic_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")

        def _boom(*_a: object, **_k: object) -> None:
            raise AssertionError("must not be called for the claude lane")

        monkeypatch.setattr(run, "assert_deterministic_tiers_green", _boom)
        ledger_path = synthetic_repo / "runs.jsonl"
        deps = run.RunDeps(
            spawn=RecordingSpawn(),
            clock=lambda: date(2026, 9, 13),
            ledger_path=ledger_path,
            quota_path=synthetic_repo / "missing-quota.md",  # would blow up if ever touched
        )

        assert run.run_trials(_run_args(platform="claude"), deps) == 0

    def test_a_sporadic_lane_refuses_before_any_trial_when_tiers_are_red(
        self, synthetic_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")

        def _red(*_a: object, **_k: object) -> None:
            raise RuntimeError("Tier A/A2 are not green")

        monkeypatch.setattr(run, "assert_deterministic_tiers_green", _red)
        spy = RecordingSpawn()
        deps = run.RunDeps(spawn=spy, clock=lambda: date(2026, 9, 13))

        with pytest.raises(RuntimeError, match="not green"):
            run.run_trials(_run_args(platform="codex"), deps)
        assert spy.calls == []

    def test_a_sporadic_lane_refuses_when_the_weekly_allowance_is_spent(
        self, synthetic_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        monkeypatch.setattr(run, "assert_deterministic_tiers_green", lambda *_a, **_k: None)
        quota_path = synthetic_repo / "quota.md"
        spend = "| 2026-09-07 | codex | s | c | 2026-W37 |\n"
        quota_path.write_text(_quota_markdown(1, spend), encoding="utf-8")
        spy = RecordingSpawn()
        deps = run.RunDeps(spawn=spy, clock=lambda: date(2026, 9, 7), quota_path=quota_path)

        with pytest.raises(RuntimeError, match="no override"):
            run.run_trials(_run_args(platform="codex"), deps)
        assert spy.calls == []

    def test_a_sporadic_lane_records_spend_after_a_trial_when_allowance_remains(
        self, synthetic_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        monkeypatch.setattr(run, "assert_deterministic_tiers_green", lambda *_a, **_k: None)
        quota_path = synthetic_repo / "quota.md"
        quota_path.write_text(_quota_markdown(4), encoding="utf-8")
        deps = run.RunDeps(
            spawn=RecordingSpawn(),
            clock=lambda: date(2026, 9, 7),
            ledger_path=synthetic_repo / "runs.jsonl",
            quota_path=quota_path,
        )

        assert run.run_trials(_run_args(platform="codex"), deps) == 0

        assert "| 2026-09-07 | codex | demo-skill | happy-path | 2026-W37 |" in (
            quota_path.read_text(encoding="utf-8")
        )

    def test_multiple_trials_each_append_a_ledger_row(self, synthetic_repo: Path) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        ledger_path = synthetic_repo / "runs.jsonl"
        deps = run.RunDeps(
            spawn=RecordingSpawn(), clock=lambda: date(2026, 9, 13), ledger_path=ledger_path
        )

        assert run.run_trials(_run_args(platform="claude", trials=3), deps) == 0

        rows = ledger_path.read_text(encoding="utf-8").splitlines()
        assert len(rows) == 3

    def test_raises_when_the_case_has_no_prompt(self, synthetic_repo: Path) -> None:
        with pytest.raises(FileNotFoundError, match="No case found"):
            run.run_trials(_run_args(skill="missing-skill", platform="claude"))


class TestMain:
    def test_parses_argv_and_delegates_to_run_trials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, object] = {}

        def fake_run_trials(args: run.RunArgs, deps: run.RunDeps | None = None) -> int:
            captured["args"] = args
            return 0

        monkeypatch.setattr(run, "run_trials", fake_run_trials)
        exit_code = run.main(
            ["--skill", "s", "--case", "c", "--platform", "claude", "--model", "haiku"]
        )
        assert exit_code == 0
        assert captured["args"] == run.RunArgs(
            skill="s",
            case_name="c",
            platform="claude",
            model="haiku",
            agent_command=None,
            trials=1,
        )

    def test_falls_back_to_sys_argv_when_argv_is_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sys,
            "argv",
            ["run.py", "--skill", "s", "--case", "c", "--platform", "claude", "--model", "haiku"],
        )
        monkeypatch.setattr(run, "run_trials", lambda args, deps=None: 0)
        assert run.main() == 0
