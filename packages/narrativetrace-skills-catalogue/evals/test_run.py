# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path

import agent_turns
import isolated_agent_config
import pytest
import registry_delivery
import run
from platform_presets import preset_agent_command
from quota import QuotaSpendRow


class RecordingSpawn:
    """A fake ``Spawner``: records every ``(argv, cwd, env, stdout_to)`` call, no real subprocess.
    Can be told to raise for the grader step, an agent turn, or any other command (a registry
    pre-step, the checkout build), so a test drives pass/fail/crash without a real CLI.

    **Classified by ROLE, not by program name.** The grader is ``sh <verify.sh>``; an agent turn is
    the one call that streams into the transcript (``stdout_to`` set); everything else runs before
    the agent. Name-based classification was ambiguous where a preset shares a program with a
    pre-step -- ``claude`` is both the marketplace pre-step's program and the Claude preset's -- and
    an adversarial test once asserted "the agent never ran" while it had."""

    def __init__(
        self,
        *,
        agent_raises: Exception | None = None,
        grader_raises: Exception | None = None,
        pre_step_raises: Exception | None = None,
        on_call: Callable[[list[str], Path, Mapping[str, str]], None] | None = None,
    ) -> None:
        self.calls: list[tuple[list[str], Path]] = []
        self.envs: list[dict[str, str]] = []
        self.stdout_targets: list[Path | None] = []
        self._agent_raises = agent_raises
        self._grader_raises = grader_raises
        self._pre_step_raises = pre_step_raises
        self._on_call = on_call

    def __call__(
        self,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str],
        stdout_to: Path | None = None,
    ) -> None:
        argv_list = list(argv)
        self.calls.append((argv_list, cwd))
        self.envs.append(dict(env))
        self.stdout_targets.append(stdout_to)
        if self._on_call is not None:
            self._on_call(argv_list, cwd, env)
        raises = {
            "grader": self._grader_raises,
            "agent": self._agent_raises,
            "pre-step": self._pre_step_raises,
        }[self._role(len(self.calls) - 1)]
        if raises is not None:
            raise raises

    def _role(self, index: int) -> str:
        if self.calls[index][0][:1] == ["sh"]:
            return "grader"
        return "agent" if self.stdout_targets[index] is not None else "pre-step"

    def _calls_in(self, role: str) -> list[tuple[list[str], Path]]:
        return [call for i, call in enumerate(self.calls) if self._role(i) == role]

    @property
    def agent_calls(self) -> list[tuple[list[str], Path]]:
        return self._calls_in("agent")

    @property
    def grader_calls(self) -> list[tuple[list[str], Path]]:
        return self._calls_in("grader")

    @property
    def pre_step_calls(self) -> list[tuple[list[str], Path]]:
        return self._calls_in("pre-step")


@pytest.fixture(autouse=True)
def stand_in_login(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Every trial seeds a login now, so EVERY test gets a stand-in for the operator's real vendor
    configuration: no test here reads the one on this machine, let alone copies its secret. Outside
    ``tmp_path``, which some tests list."""
    real = tmp_path_factory.mktemp("stand-in-real-config")
    (real / ".credentials.json").write_text('{"token":"t"}', encoding="utf-8")
    monkeypatch.setattr(run, "real_config_dir", lambda: real)
    return real


@pytest.fixture
def synthetic_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Points run.py's module-relative path constants at a throwaway repo layout so the trial-flow
    tests never touch this repo's own fixtures or case content. Deliberate: under
    ``mutmut``, the mutated copy of ``run.py`` lives at a different depth (``mutants/evals/``),
    which changes what ``_REPO_ROOT``/``_EVALS_DIR`` resolve to — any test that depended on the
    real repo tree via those constants would fail for every mutant, not just a real regression."""
    repo_root = tmp_path / "repo"
    evals_dir = repo_root / "packages" / "narrativetrace-skills-catalogue" / "evals"
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
    registry: str | None = None,
) -> None:
    """Populates a case directory (prompt + graders/) under ``synthetic_repo``'s evals tree, and a
    fixture directory under its repo root, mirroring the real layout closely enough for
    ``run_trials``/``_run_one_trial`` to exercise the whole flow. ``registry`` declares the case a
    registry one, exactly as a real ``case.json`` does."""
    case_dir = (
        repo_root / "packages" / "narrativetrace-skills-catalogue" / "evals" / skill / case_name
    )
    (case_dir / "graders").mkdir(parents=True)
    (case_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    manifest: dict[str, str] = {"fixture": fixture}
    if registry is not None:
        manifest["registry"] = registry
    (case_dir / "case.json").write_text(json.dumps(manifest), encoding="utf-8")
    fixture_src = repo_root / fixture
    fixture_src.mkdir(parents=True)
    (fixture_src / "marker.txt").write_text("fixture-content", encoding="utf-8")


def _with_rendered_pages(repo_root: Path) -> Path:
    """Gives ``synthetic_repo`` both rendered page layouts, so a test can prove that a registry case
    is handed NEITHER of them."""
    for layout in (".agents", ".claude"):
        page = repo_root / layout / "skills" / "example" / "SKILL.md"
        page.parent.mkdir(parents=True)
        page.write_text("---\nname: example\n---\n", encoding="utf-8")
    return repo_root


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
        run.default_spawner(["true"], tmp_path, {})  # must not raise

    def test_raises_on_a_nonzero_exit(self, tmp_path: Path) -> None:
        with pytest.raises(subprocess.CalledProcessError):
            run.default_spawner(["false"], tmp_path, {})

    def test_argv_elements_are_not_shell_parsed(self, tmp_path: Path) -> None:
        # If this ran through a shell, "&&" would separate two commands and create two files;
        # passed as argv it is one filename, proving no shell ever re-parses an argv element.
        run.default_spawner(["touch", "a && touch pwned.txt"], tmp_path, {})
        assert [p.name for p in tmp_path.iterdir()] == ["a && touch pwned.txt"]

    def test_the_injected_environment_reaches_the_real_child_process(self, tmp_path: Path) -> None:
        """Proven at the actual OS process boundary, not against a fake: the whole point of the
        isolation is that the vendor CLI in a child process reads the trial's own directory."""
        run.default_spawner(
            [
                sys.executable,
                "-c",
                "import os, pathlib; pathlib.Path('seen.txt').write_text(os.environ['NT_PROBE'])",
            ],
            tmp_path,
            {"NT_PROBE": "the trials own config"},
        )

        assert (tmp_path / "seen.txt").read_text(encoding="utf-8") == "the trials own config"

    def test_the_ambient_environment_survives_the_injection(self, tmp_path: Path) -> None:
        """Merged over the ambient environment, never replacing it: a vendor CLI that lost ``PATH``
        or ``HOME`` would fail for a reason the case never touched."""
        run.default_spawner(
            [
                sys.executable,
                "-c",
                "import os, pathlib; pathlib.Path('seen.txt').write_text("
                "f\"{bool(os.environ.get('PATH'))}{bool(os.environ.get('HOME'))}\")",
            ],
            tmp_path,
            {"NT_PROBE": "x"},
        )

        assert (tmp_path / "seen.txt").read_text(encoding="utf-8") == "TrueTrue"


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


class TestScaffoldingAFixtureThatIsNotThere:
    def test_leaves_no_scratch_directory_behind(
        self, synthetic_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The scratch directory exists before the copy that fails, so without cleanup every
        mistyped fixture path leaves an empty ``nt-eval-*`` behind (237 had piled up in /tmp)."""
        scratch_root = tmp_path / "tmp"
        scratch_root.mkdir()
        monkeypatch.setattr(tempfile, "tempdir", str(scratch_root))

        with pytest.raises(FileNotFoundError):
            run._scaffold_fixture("fixtures/not-there")

        assert list(scratch_root.iterdir()) == []


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

    def test_the_claude_presets_tool_list_stays_one_argument(self) -> None:
        """The quoted tool list is one argv element or none of it reaches the CLI: a
        comma-separated list split across five arguments is a different command."""
        preset = preset_agent_command("claude", "haiku", "add-narrative-tracing")

        argv = run._tokenize_agent_command(preset, "do it")

        assert argv == [
            "claude",
            "-p",
            "do it",
            "--model",
            "haiku",
            "--allowed-tools",
            "Bash,Read,Edit,Write,WebFetch,Skill",
            "--output-format",
            "stream-json",
            "--verbose",
            "--strict-mcp-config",
        ]


class TestRunGrader:
    def test_pass_when_spawn_succeeds(self, tmp_path: Path) -> None:
        case_dir = tmp_path / "case"
        spy = RecordingSpawn()
        assert run._run_grader(case_dir, tmp_path, spy, {}) == "pass"
        assert spy.calls == [(["sh", str(case_dir / "graders" / "verify.sh")], tmp_path)]

    def test_fail_when_spawn_raises_called_process_error(self, tmp_path: Path) -> None:
        case_dir = tmp_path / "case"
        spy = RecordingSpawn(grader_raises=subprocess.CalledProcessError(1, ["sh"]))
        assert run._run_grader(case_dir, tmp_path, spy, {}) == "fail"

    def test_fail_when_spawn_raises_os_error(self, tmp_path: Path) -> None:
        case_dir = tmp_path / "case"
        spy = RecordingSpawn(grader_raises=OSError("no such file"))
        assert run._run_grader(case_dir, tmp_path, spy, {}) == "fail"


class TestTheGradersOwnEnvironment:
    """What only a grader may know, never the agent: where the installer THIS CHECKOUT provides
    lives. A registry case's adoption proof has to read that installer rather than the one the
    project resolved from PyPI, because the published release predates the adoption behaviour the
    proof is about — and an agent handed the same pointer could install from the checkout, which is
    not what any reader has."""

    def test_the_grader_is_told_where_this_checkouts_installer_lives(
        self, synthetic_repo: Path
    ) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        spy = RecordingSpawn()
        deps = run.RunDeps(
            spawn=spy, clock=lambda: date(2026, 10, 7), ledger_path=synthetic_repo / "runs.jsonl"
        )

        run._run_one_trial(
            _run_args(), run._EVALS_DIR / "demo-skill" / "happy-path", "the prompt", 1, deps
        )

        grader_env = spy.envs[spy.calls.index(spy.grader_calls[0])]
        assert grader_env["NARRATIVETRACE_CLI_PROJECT"] == str(synthetic_repo)

    def test_the_agent_is_never_told(self, synthetic_repo: Path) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        spy = RecordingSpawn()
        deps = run.RunDeps(
            spawn=spy, clock=lambda: date(2026, 10, 7), ledger_path=synthetic_repo / "runs.jsonl"
        )

        run._run_one_trial(
            _run_args(), run._EVALS_DIR / "demo-skill" / "happy-path", "the prompt", 1, deps
        )

        agent_env = spy.envs[spy.calls.index(spy.agent_calls[0])]
        assert "NARRATIVETRACE_CLI_PROJECT" not in agent_env

    def test_a_registry_graders_environment_is_the_isolated_one_plus_that_pointer(
        self, synthetic_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = tmp_path / "real-config"
        real.mkdir()
        monkeypatch.setattr(run, "real_config_dir", lambda: real)
        _add_case(synthetic_repo, "demo-skill", "registry-npx-skills", registry="npx-skills")
        spy = RecordingSpawn()
        deps = run.RunDeps(
            spawn=spy, clock=lambda: date(2026, 10, 7), ledger_path=synthetic_repo / "runs.jsonl"
        )

        run._run_one_trial(
            _run_args(case_name="registry-npx-skills"),
            run._EVALS_DIR / "demo-skill" / "registry-npx-skills",
            "the prompt",
            1,
            deps,
        )

        grader_env = spy.envs[spy.calls.index(spy.grader_calls[0])]
        work = Path(grader_env["CLAUDE_CONFIG_DIR"]).parent
        assert grader_env == {
            **isolated_agent_config.env(work),
            "PATH": f"{work / 'bin'}:{os.environ['PATH']}",
            "PYTHONDONTWRITEBYTECODE": "1",
            "NARRATIVETRACE_TRANSCRIPT": str(work / "transcript.jsonl"),
            "NARRATIVETRACE_GH_LOG": str(work / "gh-invocations.log"),
            "NARRATIVETRACE_CLI_PROJECT": str(synthetic_repo),
        }


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
        monkeypatch.setattr(agent_turns, "preset_agent_command", lambda *_a, **_k: "")
        ledger_path = synthetic_repo / "runs.jsonl"
        spy = RecordingSpawn()
        deps = run.RunDeps(spawn=spy, clock=lambda: date(2026, 9, 13), ledger_path=ledger_path)
        case_dir = run._EVALS_DIR / "demo-skill" / "happy-path"

        run._run_one_trial(_run_args(agent_command=None), case_dir, "the prompt", 1, deps)

        assert spy.agent_calls == []
        assert spy.grader_calls != []
        assert "skipping the agent step" in capsys.readouterr().out


class TestARegistryCase:
    """A registry case measures the state a registry left behind, so the harness has to keep its
    own hands off the project, run the registry's documented commands first, and do all of it in a
    vendor configuration the trial owns."""

    @pytest.fixture
    def seeded_login(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """A stand-in for the operator's real vendor configuration, so no test reads or writes the
        one on this machine."""
        real = tmp_path / "real-config"
        real.mkdir()
        (real / ".credentials.json").write_text('{"token":"t"}', encoding="utf-8")
        monkeypatch.setattr(run, "real_config_dir", lambda: real)
        return real

    @staticmethod
    def _deps(repo_root: Path, spy: RecordingSpawn) -> run.RunDeps:
        return run.RunDeps(
            spawn=spy, clock=lambda: date(2026, 10, 7), ledger_path=repo_root / "runs.jsonl"
        )

    @staticmethod
    def _case_dir(skill: str = "demo-skill", case_name: str = "registry-npx-skills") -> Path:
        return run._EVALS_DIR / skill / case_name

    def test_never_gets_the_harnesss_own_copy_of_the_rendered_pages(
        self, synthetic_repo: Path, seeded_login: Path
    ) -> None:
        """The whole point of a registry case: the pages in the project are the ones the registry
        tool put there. A page the harness copied in on top would answer the case's own question
        for it -- and for the tool that symlinks one flavour at the other, it would answer it
        wrongly."""
        _with_rendered_pages(synthetic_repo)
        _add_case(synthetic_repo, "demo-skill", "registry-npx-skills", registry="npx-skills")
        seen: list[Path] = []
        spy = RecordingSpawn(on_call=lambda argv, cwd, env: seen.append(cwd))

        run._run_one_trial(
            _run_args(case_name="registry-npx-skills"),
            self._case_dir(),
            "the prompt",
            1,
            self._deps(synthetic_repo, spy),
        )

        scratch = seen[0]
        assert not (scratch / ".agents" / "skills").exists()
        assert not (scratch / ".claude" / "skills").exists()

    def test_runs_every_pre_step_command_in_order_in_the_project_before_the_agent(
        self, synthetic_repo: Path, seeded_login: Path
    ) -> None:
        _add_case(
            synthetic_repo,
            "demo-skill",
            "registry-claude-marketplace",
            registry="claude-marketplace",
        )
        spy = RecordingSpawn()

        run._run_one_trial(
            _run_args(case_name="registry-claude-marketplace"),
            self._case_dir(case_name="registry-claude-marketplace"),
            "the prompt",
            1,
            self._deps(synthetic_repo, spy),
        )

        work = Path(spy.envs[0]["CLAUDE_CONFIG_DIR"]).parent
        expected = registry_delivery.commands_for(
            "claude-marketplace", synthetic_repo, work / "staged"
        )
        assert [tuple(argv) for argv, _ in spy.pre_step_calls] == list(expected)
        assert [cwd for _, cwd in spy.pre_step_calls] == [spy.calls[0][1]] * len(expected)
        assert len(spy.agent_calls) == 1
        assert len(spy.grader_calls) == 1
        # the pre-step ran before both of them
        assert spy.calls.index(spy.agent_calls[0]) > len(expected) - 1

    def test_creates_the_staged_trees_directory_before_any_pre_step_command_runs(
        self, synthetic_repo: Path, seeded_login: Path
    ) -> None:
        """``git archive -o <staged>.tar`` needs the parent, and ``tar -C <staged>`` needs the
        directory itself."""
        _add_case(synthetic_repo, "demo-skill", "registry-npx-skills", registry="npx-skills")
        staged_seen: list[bool] = []

        def _check(argv: list[str], cwd: Path, env: Mapping[str, str]) -> None:
            work = Path(env["CLAUDE_CONFIG_DIR"]).parent
            staged_seen.append((work / "staged").is_dir())

        spy = RecordingSpawn(on_call=_check)

        run._run_one_trial(
            _run_args(case_name="registry-npx-skills"),
            self._case_dir(),
            "the prompt",
            1,
            self._deps(synthetic_repo, spy),
        )

        assert staged_seen and all(staged_seen)

    def test_every_command_of_the_trial_sees_the_isolated_configuration(
        self, synthetic_repo: Path, seeded_login: Path
    ) -> None:
        """Pre-step, agent and grader alike: a marketplace and a plugin are user-level state, and
        the operator's own configuration is neither written to nor read from."""
        _add_case(synthetic_repo, "demo-skill", "registry-npx-skills", registry="npx-skills")
        spy = RecordingSpawn()

        run._run_one_trial(
            _run_args(case_name="registry-npx-skills"),
            self._case_dir(),
            "the prompt",
            1,
            self._deps(synthetic_repo, spy),
        )

        work = Path(spy.envs[0]["CLAUDE_CONFIG_DIR"]).parent
        isolated = isolated_agent_config.env(work)
        for env in spy.envs:
            assert {key: env[key] for key in isolated} == isolated
        assert str(seeded_login) not in spy.envs[0]["CLAUDE_CONFIG_DIR"]

    def test_seeds_the_subscription_login_into_that_configuration(
        self, synthetic_repo: Path, seeded_login: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A fresh configuration is a logged-out one: without this the agent answers "Not logged
        in" and the trial measures the harness instead of the registry."""
        _add_case(synthetic_repo, "demo-skill", "registry-npx-skills", registry="npx-skills")
        logins: list[str] = []

        def _read_login(argv: list[str], cwd: Path, env: Mapping[str, str]) -> None:
            login = Path(env["CLAUDE_CONFIG_DIR"]) / ".credentials.json"
            logins.append(login.read_text(encoding="utf-8") if login.is_file() else "")

        spy = RecordingSpawn(on_call=_read_login)

        run._run_one_trial(
            _run_args(case_name="registry-npx-skills"),
            self._case_dir(),
            "the prompt",
            1,
            self._deps(synthetic_repo, spy),
        )

        assert logins[0] == '{"token":"t"}'
        assert "subscription login seeded" in capsys.readouterr().out

    def test_says_so_when_there_is_no_login_to_seed(
        self,
        synthetic_repo: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A trial with no login does not fail here -- it fails three steps later inside the agent,
        a long way from the cause -- so the runner says which outcome it got."""
        empty = tmp_path / "empty-config"
        empty.mkdir()
        monkeypatch.setattr(run, "real_config_dir", lambda: empty)
        _add_case(synthetic_repo, "demo-skill", "registry-npx-skills", registry="npx-skills")

        run._run_one_trial(
            _run_args(case_name="registry-npx-skills"),
            self._case_dir(),
            "the prompt",
            1,
            self._deps(synthetic_repo, RecordingSpawn()),
        )

        assert "NO login found" in capsys.readouterr().out

    def test_a_failed_pre_step_crashes_the_trial_and_leaves_no_ledger_row(
        self, synthetic_repo: Path, seeded_login: Path
    ) -> None:
        """A pre-step that failed delivered nothing, so there is no registry state to grade -- the
        trial CRASHED, the way a crashed agent command does. A red row saying "the registry path
        does not work" when the vendor tool was simply absent is worse than no row at all."""
        _add_case(synthetic_repo, "demo-skill", "registry-npx-skills", registry="npx-skills")
        ledger_path = synthetic_repo / "runs.jsonl"
        spy = RecordingSpawn(pre_step_raises=subprocess.CalledProcessError(42, ["git"]))

        with pytest.raises(RuntimeError, match="registry pre-step"):
            run._run_one_trial(
                _run_args(case_name="registry-npx-skills"),
                self._case_dir(),
                "the prompt",
                1,
                self._deps(synthetic_repo, spy),
            )

        assert not ledger_path.exists()
        assert len(spy.pre_step_calls) == 1  # it stopped at the first failure
        assert spy.agent_calls == []
        assert spy.grader_calls == []

    def test_an_absent_vendor_tool_crashes_the_trial_too(
        self, synthetic_repo: Path, seeded_login: Path
    ) -> None:
        """The same reading for a tool that cannot even launch: an absent `npx` is not a verdict
        about the registry path."""
        _add_case(synthetic_repo, "demo-skill", "registry-npx-skills", registry="npx-skills")
        spy = RecordingSpawn(pre_step_raises=OSError("no such file: npx"))

        with pytest.raises(RuntimeError, match="registry pre-step"):
            run._run_one_trial(
                _run_args(case_name="registry-npx-skills"),
                self._case_dir(),
                "the prompt",
                1,
                self._deps(synthetic_repo, spy),
            )

        assert not (synthetic_repo / "runs.jsonl").exists()

    def test_deletes_its_work_directory_whatever_the_outcome(
        self, synthetic_repo: Path, seeded_login: Path
    ) -> None:
        _add_case(synthetic_repo, "demo-skill", "registry-npx-skills", registry="npx-skills")
        spy = RecordingSpawn()

        run._run_one_trial(
            _run_args(case_name="registry-npx-skills"),
            self._case_dir(),
            "the prompt",
            1,
            self._deps(synthetic_repo, spy),
        )

        work = Path(spy.envs[0]["CLAUDE_CONFIG_DIR"]).parent
        assert not work.exists()

    def test_deletes_its_work_directory_after_a_crash(
        self, synthetic_repo: Path, seeded_login: Path
    ) -> None:
        _add_case(synthetic_repo, "demo-skill", "registry-npx-skills", registry="npx-skills")
        spy = RecordingSpawn(pre_step_raises=OSError("boom"))

        with pytest.raises(RuntimeError):
            run._run_one_trial(
                _run_args(case_name="registry-npx-skills"),
                self._case_dir(),
                "the prompt",
                1,
                self._deps(synthetic_repo, spy),
            )

        work = Path(spy.envs[0]["CLAUDE_CONFIG_DIR"]).parent
        assert not work.exists()

    def test_each_trial_gets_its_own_vendor_configuration(
        self, synthetic_repo: Path, seeded_login: Path
    ) -> None:
        """Three trials of one registry case are three installs, not one: a marketplace left over
        from the previous trial would make the second trial's pre-step a no-op, and its row would
        then be about a tree the registry tool did not build in that run."""
        _add_case(synthetic_repo, "demo-skill", "registry-npx-skills", registry="npx-skills")
        spy = RecordingSpawn()
        deps = self._deps(synthetic_repo, spy)
        args = _run_args(case_name="registry-npx-skills")

        run._run_one_trial(args, self._case_dir(), "the prompt", 1, deps)
        run._run_one_trial(args, self._case_dir(), "the prompt", 2, deps)

        configurations = {env["CLAUDE_CONFIG_DIR"] for env in spy.envs}
        assert len(configurations) == 2

    def test_refuses_a_case_declaring_a_registry_outside_the_vocabulary(
        self, synthetic_repo: Path
    ) -> None:
        """Never read as "no registry": a case that silently skipped its pre-step would pass as a
        plain prompt replay while its name and its ledger row still claimed a registry."""
        _add_case(synthetic_repo, "demo-skill", "registry-gemini", registry="gemini-skills")
        spy = RecordingSpawn()

        with pytest.raises(ValueError, match="gemini-skills"):
            run._run_one_trial(
                _run_args(case_name="registry-gemini"),
                self._case_dir(case_name="registry-gemini"),
                "the prompt",
                1,
                self._deps(synthetic_repo, spy),
            )

        assert spy.calls == []


class TestAnOrdinaryCase:
    def test_runs_no_pre_step_and_its_agent_sees_only_the_trials_own_environment(
        self, synthetic_repo: Path
    ) -> None:
        """No registry pre-step -- but every trial, ordinary or not, runs behind the recording
        stand-ins and against a throwaway agent configuration (Java's cross-port items 4 and 5)."""
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        spy = RecordingSpawn()
        deps = run.RunDeps(
            spawn=spy, clock=lambda: date(2026, 10, 7), ledger_path=synthetic_repo / "runs.jsonl"
        )

        run._run_one_trial(
            _run_args(), run._EVALS_DIR / "demo-skill" / "happy-path", "the prompt", 1, deps
        )

        assert spy.pre_step_calls == []
        agent_env = spy.envs[spy.calls.index(spy.agent_calls[0])]
        assert sorted(agent_env) == ["CLAUDE_CONFIG_DIR", "PATH", "PYTHONDONTWRITEBYTECODE"]


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


_SESSION = "0f8fad5b-d9cb-469f-a165-70867728950e"


def _trial_deps(repo_root: Path, spy: RecordingSpawn) -> run.RunDeps:
    return run.RunDeps(
        spawn=spy,
        clock=lambda: date(2026, 10, 8),
        ledger_path=repo_root / "runs.jsonl",
        new_session_id=lambda: _SESSION,
        evidence_root=repo_root / "kept-evidence",
    )


def _with_manifest(repo_root: Path, skill: str, case_name: str, **fields: object) -> Path:
    """Adds ``fields`` to an existing case's ``case.json``."""
    case_dir = run._EVALS_DIR / skill / case_name
    manifest = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    manifest.update(fields)
    (case_dir / "case.json").write_text(json.dumps(manifest), encoding="utf-8")
    return case_dir


def _agent_writes(text: str) -> Callable[[list[str], Path, Mapping[str, str]], None]:
    """An ``on_call`` that plays the agent: it appends ``text`` to the transcript the runner hands
    its turn. The spy cannot see ``stdout_to`` in ``on_call``, so it finds the file the grader will
    be told about instead -- the one place both must agree."""

    def _write(argv: list[str], cwd: Path, env: Mapping[str, str]) -> None:
        if argv[:1] in (["sh"], ["uv"]):
            return
        work = Path(env["CLAUDE_CONFIG_DIR"]).parent
        with (work / "transcript.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")

    return _write


class TestEveryTrialRecords:
    def test_the_agents_turn_streams_into_the_transcript_outside_the_project(
        self, synthetic_repo: Path
    ) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        spy = RecordingSpawn()

        run._run_one_trial(
            _run_args(),
            run._EVALS_DIR / "demo-skill" / "happy-path",
            "p",
            1,
            _trial_deps(synthetic_repo, spy),
        )

        agent_index = spy.calls.index(spy.agent_calls[0])
        transcript = spy.stdout_targets[agent_index]
        scratch = spy.agent_calls[0][1]
        assert transcript is not None
        assert transcript.name == "transcript.jsonl"
        assert scratch not in transcript.parents
        assert spy.stdout_targets[spy.calls.index(spy.grader_calls[0])] is None

    def test_the_grader_alone_is_told_where_the_evidence_is(self, synthetic_repo: Path) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        spy = RecordingSpawn()

        run._run_one_trial(
            _run_args(),
            run._EVALS_DIR / "demo-skill" / "happy-path",
            "p",
            1,
            _trial_deps(synthetic_repo, spy),
        )

        agent_env = spy.envs[spy.calls.index(spy.agent_calls[0])]
        grader_env = spy.envs[spy.calls.index(spy.grader_calls[0])]
        agent_index = spy.calls.index(spy.agent_calls[0])
        assert "NARRATIVETRACE_TRANSCRIPT" not in agent_env
        assert "NARRATIVETRACE_GH_LOG" not in agent_env
        assert grader_env["NARRATIVETRACE_TRANSCRIPT"] == str(spy.stdout_targets[agent_index])
        assert grader_env["NARRATIVETRACE_GH_LOG"].endswith("gh-invocations.log")
        assert grader_env["PATH"] == agent_env["PATH"]

    def test_the_stand_ins_come_first_on_the_agents_path(self, synthetic_repo: Path) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        seen: dict[str, bool] = {}

        def _look(argv: list[str], cwd: Path, env: Mapping[str, str]) -> None:
            if argv[:1] != ["sh"]:
                first = Path(env["PATH"].split(":")[0])
                seen["gh"] = (first / "gh").is_file()
                seen["curl"] = (first / "curl").is_file()

        run._run_one_trial(
            _run_args(),
            run._EVALS_DIR / "demo-skill" / "happy-path",
            "p",
            1,
            _trial_deps(synthetic_repo, RecordingSpawn(on_call=_look)),
        )

        assert seen == {"gh": True, "curl": True}

    def test_an_ordinary_case_seeds_the_login_into_its_own_configuration_too(
        self, synthetic_repo: Path
    ) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        logins: list[str] = []

        def _read(argv: list[str], cwd: Path, env: Mapping[str, str]) -> None:
            logins.append(
                (Path(env["CLAUDE_CONFIG_DIR"]) / ".credentials.json").read_text(encoding="utf-8")
            )

        run._run_one_trial(
            _run_args(),
            run._EVALS_DIR / "demo-skill" / "happy-path",
            "p",
            1,
            _trial_deps(synthetic_repo, RecordingSpawn(on_call=_read)),
        )

        assert logins[0] == '{"token":"t"}'

    def test_deletes_the_work_directory_whatever_the_outcome(self, synthetic_repo: Path) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        spy = RecordingSpawn(grader_raises=subprocess.CalledProcessError(1, "sh"))

        run._run_one_trial(
            _run_args(),
            run._EVALS_DIR / "demo-skill" / "happy-path",
            "p",
            1,
            _trial_deps(synthetic_repo, spy),
        )

        work = Path(spy.envs[0]["CLAUDE_CONFIG_DIR"]).parent
        assert not work.exists()


class TestKeptEvidence:
    def test_a_failed_trial_keeps_its_transcript_where_somebody_can_read_it(
        self, synthetic_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path", prompt="report it")
        spy = RecordingSpawn(
            grader_raises=subprocess.CalledProcessError(1, "sh"),
            on_call=_agent_writes('{"type":"result","result":"done"}'),
        )

        run._run_one_trial(
            _run_args(),
            run._EVALS_DIR / "demo-skill" / "happy-path",
            "report it",
            1,
            _trial_deps(synthetic_repo, spy),
        )

        kept = synthetic_repo / "kept-evidence" / "demo-skill" / "happy-path" / "trial-1"
        lines = (kept / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
        assert json.loads(lines[0]) == {"nt_turn": 1, "role": "user", "text": "report it"}
        assert json.loads(lines[1]) == {"type": "result", "result": "done"}
        assert f"evidence kept under {kept}" in capsys.readouterr().out

    def test_a_crashed_trial_keeps_its_evidence_too(self, synthetic_repo: Path) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        spy = RecordingSpawn(agent_raises=subprocess.CalledProcessError(1, "echo"))

        with pytest.raises(subprocess.CalledProcessError):
            run._run_one_trial(
                _run_args(),
                run._EVALS_DIR / "demo-skill" / "happy-path",
                "p",
                1,
                _trial_deps(synthetic_repo, spy),
            )

        kept = synthetic_repo / "kept-evidence" / "demo-skill" / "happy-path" / "trial-1"
        assert (kept / "transcript.jsonl").is_file()

    def test_a_passing_trial_keeps_its_evidence_apart_from_a_failures(
        self, synthetic_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Phase 7 cross-port item 8: a pass is evidence too — the demonstration transcript, and
        the only way to check a grader did not pass a trial for the wrong reason."""
        _add_case(synthetic_repo, "demo-skill", "happy-path", prompt="p")
        spy = RecordingSpawn(on_call=_agent_writes('{"type":"result","result":"done"}'))

        run._run_one_trial(
            _run_args(),
            run._EVALS_DIR / "demo-skill" / "happy-path",
            "p",
            1,
            _trial_deps(synthetic_repo, spy),
        )

        trial_dir = synthetic_repo / "kept-evidence" / "demo-skill" / "happy-path"
        assert (trial_dir / "trial-1-pass" / "transcript.jsonl").is_file()
        assert not (trial_dir / "trial-1").exists()
        assert f"evidence kept under {trial_dir / 'trial-1-pass'}" in capsys.readouterr().out

    def test_the_production_root_is_this_packages_ignored_build_directory(self) -> None:
        assert run.RunDeps().evidence_root == run._EVALS_DIR.parent / "build" / "evals"


class TestAMultiTurnCase:
    def _case(self, repo_root: Path, turns: dict[str, str]) -> Path:
        _add_case(repo_root, "demo-skill", "approval", prompt="report it")
        return _with_manifest(repo_root, "demo-skill", "approval", turns=turns)

    def test_drives_every_scripted_turn_as_one_conversation(self, synthetic_repo: Path) -> None:
        case_dir = self._case(synthetic_repo, {"2": "yes, file it", "3": "thanks"})
        spy = RecordingSpawn()

        run._run_one_trial(
            _run_args(case_name="approval", agent_command=None, model="claude-haiku-5-5"),
            case_dir,
            "report it",
            1,
            _trial_deps(synthetic_repo, spy),
        )

        argvs = [argv for argv, _ in spy.agent_calls]
        assert [argv[2] for argv in argvs] == ["report it", "yes, file it", "thanks"]
        assert argvs[0][-2:] == ["--session-id", _SESSION]
        assert argvs[1][-2:] == ["--resume", _SESSION]
        assert argvs[2][-2:] == ["--resume", _SESSION]
        assert len(spy.grader_calls) == 1

    def test_writes_the_users_words_before_each_turns_own_output(
        self, synthetic_repo: Path
    ) -> None:
        case_dir = self._case(synthetic_repo, {"2": "no, do not file it"})
        spy = RecordingSpawn(
            grader_raises=subprocess.CalledProcessError(1, "sh"),
            on_call=_agent_writes('{"type":"result","result":"turn output"}'),
        )

        run._run_one_trial(
            _run_args(case_name="approval", agent_command=None),
            case_dir,
            "report it",
            1,
            _trial_deps(synthetic_repo, spy),
        )

        kept = synthetic_repo / "kept-evidence" / "demo-skill" / "approval" / "trial-1"
        events = [
            json.loads(line)
            for line in (kept / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert [event.get("nt_turn", event.get("result")) for event in events] == [
            1,
            "turn output",
            2,
            "turn output",
        ]
        assert events[2]["text"] == "no, do not file it"

    def test_a_turn_that_fails_stops_the_conversation_before_any_later_turn_or_grade(
        self, synthetic_repo: Path
    ) -> None:
        """A second turn driven after a failed first is an approval answering a question that was
        never asked, and its grader would read "nothing was filed" as a pass."""
        case_dir = self._case(synthetic_repo, {"2": "yes"})
        spy = RecordingSpawn(agent_raises=subprocess.CalledProcessError(1, "claude"))

        with pytest.raises(subprocess.CalledProcessError):
            run._run_one_trial(
                _run_args(case_name="approval", agent_command=None),
                case_dir,
                "report it",
                1,
                _trial_deps(synthetic_repo, spy),
            )

        assert len(spy.agent_calls) == 1
        assert spy.grader_calls == []
        assert not (synthetic_repo / "runs.jsonl").exists()

    def test_refuses_an_override_before_anything_runs(self, synthetic_repo: Path) -> None:
        case_dir = self._case(synthetic_repo, {"2": "yes"})
        spy = RecordingSpawn()

        with pytest.raises(ValueError, match=r"\Aa multi-turn case runs on its platform's preset"):
            run._run_one_trial(
                _run_args(case_name="approval", agent_command="echo {prompt}"),
                case_dir,
                "report it",
                1,
                _trial_deps(synthetic_repo, spy),
            )

        assert spy.calls == []

    def test_each_trial_opens_a_fresh_session(self, synthetic_repo: Path) -> None:
        case_dir = self._case(synthetic_repo, {"2": "yes"})
        ids = iter(["11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"])
        spy = RecordingSpawn()
        deps = run.RunDeps(
            spawn=spy,
            clock=lambda: date(2026, 10, 8),
            ledger_path=synthetic_repo / "runs.jsonl",
            new_session_id=lambda: next(ids),
            evidence_root=synthetic_repo / "kept",
        )

        for trial in (1, 2):
            run._run_one_trial(
                _run_args(case_name="approval", agent_command=None), case_dir, "r", trial, deps
            )

        opened = [argv[-1] for argv, _ in spy.agent_calls if "--session-id" in argv]
        assert opened == [
            "11111111-1111-4111-8111-111111111111",
            "22222222-2222-4222-8222-222222222222",
        ]

    def test_the_production_session_id_is_a_fresh_uuid(self) -> None:
        first, second = run.RunDeps().new_session_id(), run.RunDeps().new_session_id()
        assert first != second
        assert agent_turns.AgentTurns.of("claude", "m", "s", None, "p", ["yes"], first)


class TestTheCheckoutInstall:
    """A case declaring ``"install": "checkout"`` measures behaviour the PUBLISHED release predates
    (the feedback verb shipped after 0.2.0): the agent's own ``uv`` must resolve this checkout's
    build, and the skill pages must be this checkout's rendered ones."""

    def _case(self, repo_root: Path, **fields: object) -> Path:
        _add_case(repo_root, "demo-skill", "from-checkout")
        _with_rendered_pages(repo_root)
        return _with_manifest(repo_root, "demo-skill", "from-checkout", **fields)

    def test_builds_every_wheel_outside_the_project_before_the_agent_runs(
        self, synthetic_repo: Path
    ) -> None:
        case_dir = self._case(synthetic_repo, install="checkout")
        spy = RecordingSpawn()

        run._run_one_trial(
            _run_args(case_name="from-checkout"), case_dir, "p", 1, _trial_deps(synthetic_repo, spy)
        )

        build_argv, build_cwd = spy.calls[0]
        work = Path(spy.envs[1]["CLAUDE_CONFIG_DIR"]).parent
        assert build_argv == [
            "uv",
            "build",
            "--wheel",
            "--all-packages",
            "-o",
            str(work / "wheels"),
        ]
        assert build_cwd == synthetic_repo
        assert spy.calls[1] == spy.agent_calls[0]

    def test_points_the_agents_own_uv_at_those_wheels(self, synthetic_repo: Path) -> None:
        case_dir = self._case(synthetic_repo, install="checkout")
        spy = RecordingSpawn()

        run._run_one_trial(
            _run_args(case_name="from-checkout"), case_dir, "p", 1, _trial_deps(synthetic_repo, spy)
        )

        work = Path(spy.envs[1]["CLAUDE_CONFIG_DIR"]).parent
        agent_env = spy.envs[spy.calls.index(spy.agent_calls[0])]
        grader_env = spy.envs[spy.calls.index(spy.grader_calls[0])]
        assert agent_env["UV_FIND_LINKS"] == str(work / "wheels")
        assert grader_env["UV_FIND_LINKS"] == str(work / "wheels")

    def test_copies_this_checkouts_rendered_pages_into_the_project(
        self, synthetic_repo: Path
    ) -> None:
        case_dir = self._case(synthetic_repo, install="checkout")
        pages: list[bool] = []

        def _look(argv: list[str], cwd: Path, env: Mapping[str, str]) -> None:
            if argv[:1] not in (["uv"], ["sh"]):
                pages.extend(
                    (cwd / layout / "skills" / "example" / "SKILL.md").is_file()
                    for layout in (".agents", ".claude")
                )

        run._run_one_trial(
            _run_args(case_name="from-checkout"),
            case_dir,
            "p",
            1,
            _trial_deps(synthetic_repo, RecordingSpawn(on_call=_look)),
        )

        assert pages == [True, True]

    def test_a_failed_build_crashes_the_trial_and_leaves_no_ledger_row(
        self, synthetic_repo: Path
    ) -> None:
        case_dir = self._case(synthetic_repo, install="checkout")

        def _fail_the_build(argv: list[str], cwd: Path, env: Mapping[str, str]) -> None:
            if argv[:1] == ["uv"]:
                raise subprocess.CalledProcessError(2, "uv")

        spy = RecordingSpawn(on_call=_fail_the_build)

        with pytest.raises(RuntimeError, match=r"\Abuilding this checkout's wheels failed"):
            run._run_one_trial(
                _run_args(case_name="from-checkout"),
                case_dir,
                "p",
                1,
                _trial_deps(synthetic_repo, spy),
            )

        assert spy.agent_calls == []
        assert not (synthetic_repo / "runs.jsonl").exists()

    def test_an_ordinary_case_resolves_the_published_release(self, synthetic_repo: Path) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        _with_rendered_pages(synthetic_repo)
        spy = RecordingSpawn()

        run._run_one_trial(
            _run_args(),
            run._EVALS_DIR / "demo-skill" / "happy-path",
            "p",
            1,
            _trial_deps(synthetic_repo, spy),
        )

        assert [argv for argv, _ in spy.calls if argv[:1] == ["uv"]] == []
        assert all("UV_FIND_LINKS" not in env for env in spy.envs)
        assert not (spy.agent_calls[0][1] / ".claude").exists()

    @pytest.mark.parametrize("install", ["published", "", 1, "pypi"])
    def test_refuses_an_install_outside_its_closed_vocabulary(
        self, synthetic_repo: Path, install: object
    ) -> None:
        case_dir = self._case(synthetic_repo, install=install)
        spy = RecordingSpawn()

        with pytest.raises(
            ValueError, match=r"declares \"install\": .* -- the only install a case"
        ):
            run._run_one_trial(
                _run_args(case_name="from-checkout"),
                case_dir,
                "p",
                1,
                _trial_deps(synthetic_repo, spy),
            )

        assert spy.calls == []

    def test_refuses_a_registry_case_that_also_installs_from_the_checkout(
        self, synthetic_repo: Path
    ) -> None:
        """A registry case's pages are the registry's, by definition; the harness copying its own
        on top would answer that case's question for it."""
        case_dir = self._case(synthetic_repo, install="checkout", registry="npx-skills")

        with pytest.raises(ValueError, match=r"declares both a registry and a checkout install"):
            run._run_one_trial(
                _run_args(case_name="from-checkout"),
                case_dir,
                "p",
                1,
                _trial_deps(synthetic_repo, RecordingSpawn()),
            )


class TestAGitRepositoryCase:
    """A case declaring ``"vcs": "git"`` is a project that already lives in a repository, as a
    real one does: a skill whose first step lists tracked files has nothing to list in a bare
    scratch copy, and the agent's improvising a ``git init`` would be measured as the skill."""

    def _case(self, repo_root: Path, **fields: object) -> Path:
        _add_case(repo_root, "demo-skill", "in-a-repository")
        return _with_manifest(repo_root, "demo-skill", "in-a-repository", **fields)

    def _git_calls(self, spy: RecordingSpawn) -> list[list[str]]:
        return [argv for argv, _ in spy.pre_step_calls if argv[:1] == ["git"]]

    def test_commits_the_fixture_in_the_project_before_the_agent_runs(
        self, synthetic_repo: Path
    ) -> None:
        case_dir = self._case(synthetic_repo, vcs="git")
        spy = RecordingSpawn()

        run._run_one_trial(
            _run_args(case_name="in-a-repository"),
            case_dir,
            "p",
            1,
            _trial_deps(synthetic_repo, spy),
        )

        verbs = ["commit" if "commit" in argv else argv[1] for argv in self._git_calls(spy)]
        assert verbs == ["init", "add", "commit"]
        assert spy.calls[2][0][:1] == ["git"]
        assert spy.calls[3] == spy.agent_calls[0]
        assert {cwd for _, cwd in spy.pre_step_calls} == {spy.agent_calls[0][1]}

    def test_stages_everything_and_names_a_throwaway_author_inline(
        self, synthetic_repo: Path
    ) -> None:
        case_dir = self._case(synthetic_repo, vcs="git")
        spy = RecordingSpawn()

        run._run_one_trial(
            _run_args(case_name="in-a-repository"),
            case_dir,
            "p",
            1,
            _trial_deps(synthetic_repo, spy),
        )

        init, add, commit = self._git_calls(spy)
        assert init == ["git", "init", "-q"]
        assert add == ["git", "add", "-A"]
        assert commit == [
            "git",
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "-m",
            "the fixture, as the project starts",
        ]

    def test_an_ordinary_case_runs_no_git(self, synthetic_repo: Path) -> None:
        _add_case(synthetic_repo, "demo-skill", "happy-path")
        spy = RecordingSpawn()

        run._run_one_trial(
            _run_args(),
            run._EVALS_DIR / "demo-skill" / "happy-path",
            "p",
            1,
            _trial_deps(synthetic_repo, spy),
        )

        assert self._git_calls(spy) == []

    @pytest.mark.parametrize("vcs", ["svn", "", 1, "GIT"])
    def test_refuses_a_vcs_outside_its_closed_vocabulary_before_anything_runs(
        self, synthetic_repo: Path, vcs: object
    ) -> None:
        case_dir = self._case(synthetic_repo, vcs=vcs)
        spy = RecordingSpawn()

        with pytest.raises(ValueError, match=r"declares \"vcs\": .* -- the only vcs a case"):
            run._run_one_trial(
                _run_args(case_name="in-a-repository"),
                case_dir,
                "p",
                1,
                _trial_deps(synthetic_repo, spy),
            )

        assert spy.calls == []

    def test_a_failed_repository_setup_crashes_the_trial_and_leaves_no_ledger_row(
        self, synthetic_repo: Path
    ) -> None:
        case_dir = self._case(synthetic_repo, vcs="git")

        def _fail_git(argv: list[str], cwd: Path, env: Mapping[str, str]) -> None:
            if argv[:1] == ["git"]:
                raise subprocess.CalledProcessError(128, "git")

        spy = RecordingSpawn(on_call=_fail_git)

        with pytest.raises(RuntimeError, match=r"\Asetting up the project's git repository failed"):
            run._run_one_trial(
                _run_args(case_name="in-a-repository"),
                case_dir,
                "p",
                1,
                _trial_deps(synthetic_repo, spy),
            )

        assert spy.agent_calls == []
        assert not (synthetic_repo / "runs.jsonl").exists()


class TestTheSpawnersHygiene:
    def test_appends_the_childs_standard_output_to_the_transcript(self, tmp_path: Path) -> None:
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text("before\n", encoding="utf-8")

        run.default_spawner(
            [sys.executable, "-c", "print('from the agent')"], tmp_path, {}, transcript
        )

        assert transcript.read_text(encoding="utf-8") == "before\nfrom the agent\n"

    def test_the_child_reads_end_of_file_rather_than_waiting_on_a_terminal(
        self, tmp_path: Path
    ) -> None:
        """The vendor CLI waits three seconds for stdin it was never going to get, every turn."""
        out = tmp_path / "out"

        run.default_spawner(
            [sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"], tmp_path, {}, out
        )

        assert out.read_text(encoding="utf-8") == "''\n"

    def test_no_trial_inherits_the_identity_of_an_agent_session_that_launched_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Launched from inside an agent session, every variable naming that session -- its id,
        its messaging socket, its effort level -- would reach the trial's own agent: a trial
        measured against the launcher, not the product."""
        for name in (
            "CLAUDECODE",
            "CLAUDE_PID",
            "CLAUDE_EFFORT",
            "CLAUDE_CODE_SESSION_ID",
            "CLAUDE_CODE_CHILD_SESSION",
            "CLAUDE_CODE_MESSAGING_SOCKET",
            "CLAUDE_CODE_MESSAGING_TOKEN",
            "CLAUDE_CODE_SESSION_ATTENDED",
            "CLAUDE_CODE_ENTRYPOINT",
            "CLAUDE_CODE_EXECPATH",
        ):
            monkeypatch.setenv(name, "the launcher's")
        monkeypatch.setenv("NT_UNRELATED", "kept")
        out = tmp_path / "out"

        run.default_spawner(
            [
                sys.executable,
                "-c",
                "import os; print(sorted(k for k in os.environ if k.startswith('CLAUDE'))"
                " + [os.environ['NT_UNRELATED']])",
            ],
            tmp_path,
            {"CLAUDE_CONFIG_DIR": "/trial/config"},
            out,
        )

        assert out.read_text(encoding="utf-8") == "['CLAUDE_CONFIG_DIR', 'kept']\n"
