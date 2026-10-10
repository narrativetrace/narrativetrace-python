# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``config.approval-mode`` — committed ``.approved.nt`` baselines with approval mode off.

The switch is read where this runtime reads it: ``NARRATIVETRACE_APPROVAL`` in the environment,
``approval`` in ``[tool.narrativetrace]``/``narrativetrace.toml``, or the variable set in live code
or configuration — never a comment, never a docstring, never a near-miss name. The value is read
as the runtime reads it (``1``/``true``/``yes``/``on``, any case, surrounding space ignored); the
NAME is case-sensitive, as an environment variable is.
"""

from __future__ import annotations

import re

import pytest
from snapshot_factory_types import MakeSnapshot

from narrativetrace_tooling.doctor.checks.approval_mode import ID, check_approval_mode
from narrativetrace_tooling.doctor.types import DoctorSnapshot

_BASELINE = {"OrderTest/places_order.approved.nt": "scenario: s\n\n#1 - A.b()\n"}


def _with_baseline(make_snapshot: MakeSnapshot, **kwargs: object) -> DoctorSnapshot:
    return make_snapshot(approved_dir_files=_BASELINE, **kwargs)


class TestNothingToCompare:
    def test_no_approval_files_passes(self, make_snapshot: MakeSnapshot) -> None:
        finding = check_approval_mode(make_snapshot())
        assert finding.id == ID == "config.approval-mode"
        assert finding.status == "pass"
        assert finding.message == (
            "no .approved.nt baselines — nothing for approval mode to compare yet"
        )

    def test_a_received_trace_alone_is_not_a_baseline(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(approved_dir_files={"T/m.received.nt": "scenario: s\n"})
        assert check_approval_mode(snapshot).status == "pass"

    def test_an_incomplete_trace_alone_is_not_a_baseline(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(approved_dir_files={"T/m.incomplete.nt": "scenario: s\n"})
        assert check_approval_mode(snapshot).status == "pass"


class TestBaselinesWithApprovalOff:
    def test_fails_and_names_the_switch(self, make_snapshot: MakeSnapshot) -> None:
        finding = check_approval_mode(_with_baseline(make_snapshot))
        assert finding.status == "fail"
        assert finding.message == (
            ".approved.nt baselines exist but approval mode is off — nothing compares them"
        )
        assert re.fullmatch(
            r"Turn approval mode on: set NARRATIVETRACE_APPROVAL=true for the test run "
            r"\(or approval = true under \[tool\.narrativetrace\] in pyproject\.toml\), then run "
            r"the whole suite: a run whose structure differs from its baseline fails and writes a "
            r"\.received\.nt to review\.",
            finding.fix,
        )

    def test_points_at_the_verify_skill(self, make_snapshot: MakeSnapshot) -> None:
        assert check_approval_mode(_with_baseline(make_snapshot)).skill == "narrativetrace-verify"

    @pytest.mark.parametrize("value", ["false", "0", "", "no", "off", "truthy", "tru"])
    def test_a_false_or_unknown_env_value_is_off(
        self, make_snapshot: MakeSnapshot, value: str
    ) -> None:
        snapshot = _with_baseline(make_snapshot, env={"NARRATIVETRACE_APPROVAL": value})
        assert check_approval_mode(snapshot).status == "fail"

    def test_the_env_name_is_case_sensitive(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = _with_baseline(make_snapshot, env={"narrativetrace_approval": "true"})
        assert check_approval_mode(snapshot).status == "fail"

    def test_a_false_config_value_is_off(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = _with_baseline(make_snapshot, narrativetrace_config={"approval": False})
        assert check_approval_mode(snapshot).status == "fail"


class TestApprovalOn:
    @pytest.mark.parametrize("value", ["true", "TRUE", " True ", "1", "yes", "on"])
    def test_the_env_switch_is_read_as_the_runtime_reads_it(
        self, make_snapshot: MakeSnapshot, value: str
    ) -> None:
        snapshot = _with_baseline(make_snapshot, env={"NARRATIVETRACE_APPROVAL": value})
        finding = check_approval_mode(snapshot)
        assert finding.status == "pass"
        assert finding.message == (
            ".approved.nt baselines exist and approval mode is on — every run compares them"
        )

    @pytest.mark.parametrize("value", [True, "true", "Yes"])
    def test_the_config_key_switches_it_on(
        self, make_snapshot: MakeSnapshot, value: object
    ) -> None:
        snapshot = _with_baseline(make_snapshot, narrativetrace_config={"approval": value})
        assert check_approval_mode(snapshot).status == "pass"

    @pytest.mark.parametrize(
        ("path", "text"),
        [
            ("conftest.py", 'import os\nos.environ["NARRATIVETRACE_APPROVAL"] = "true"\n'),
            ("conftest.py", 'import os\nos.environ.setdefault("NARRATIVETRACE_APPROVAL", "1")\n'),
            (
                "tests/conftest.py",
                "def pytest_configure(config):\n"
                "    import os\n"
                "    os.environ.update({'NARRATIVETRACE_APPROVAL': 'On'})\n",
            ),
            (
                "tests/conftest.py",
                "def f(monkeypatch):\n    monkeypatch.setenv('NARRATIVETRACE_APPROVAL', 'TRUE')\n",
            ),
            ("pytest.ini", "[pytest]\nenv =\n    NARRATIVETRACE_APPROVAL=true\n"),
            ("tox.ini", "[testenv]\nsetenv =\n    NARRATIVETRACE_APPROVAL = yes\n"),
            (
                "pyproject.toml",
                '[tool.poe.tasks.test]\ncmd = "pytest"\n'
                'env = { NARRATIVETRACE_APPROVAL = "true" }\n',
            ),
        ],
    )
    def test_live_code_or_configuration_setting_the_variable_switches_it_on(
        self, make_snapshot: MakeSnapshot, path: str, text: str
    ) -> None:
        snapshot = _with_baseline(make_snapshot, source_files={path: text})
        assert check_approval_mode(snapshot).status == "pass"


class TestNotTheSwitch:
    """Near misses: each names the switch without throwing it."""

    @pytest.mark.parametrize(
        ("path", "text"),
        [
            ("conftest.py", '# os.environ["NARRATIVETRACE_APPROVAL"] = "true"\n'),
            (
                "conftest.py",
                '"""Set NARRATIVETRACE_APPROVAL=true to compare baselines."""\n',
            ),
            ("conftest.py", 'os.environ["NARRATIVETRACE_APPROVAL"] = "false"\n'),
            ("conftest.py", 'os.environ["NARRATIVETRACE_APPROVAL_DIR"] = "true"\n'),
            ("conftest.py", 'os.environ["MY_NARRATIVETRACE_APPROVAL"] = "true"\n'),
            ("conftest.py", 'os.environ["narrativetrace_approval"] = "true"\n'),
            ("conftest.py", 'os.environ.pop("NARRATIVETRACE_APPROVAL", "true")\n'),
            ("conftest.py", 'x = ["NARRATIVETRACE_APPROVAL", "true"]\n'),
            ("conftest.py", "this is not python = NARRATIVETRACE_APPROVAL=true (\n"),
            ("pytest.ini", "[pytest]\n# env = NARRATIVETRACE_APPROVAL=true\n"),
            ("pytest.ini", "[pytest]\n; env = NARRATIVETRACE_APPROVAL=true\n"),
            ("tox.ini", "[testenv]\nsetenv = NARRATIVETRACE_APPROVAL=trueish\n"),
            ("tox.ini", "[testenv]\nsetenv = XNARRATIVETRACE_APPROVAL=true\n"),
            ("pyproject.toml", '# env = { NARRATIVETRACE_APPROVAL = "true" }\n'),
            ("README.md", "NARRATIVETRACE_APPROVAL=true\n"),
        ],
    )
    def test_a_near_miss_leaves_the_finding_failing(
        self, make_snapshot: MakeSnapshot, path: str, text: str
    ) -> None:
        snapshot = _with_baseline(make_snapshot, source_files={path: text})
        assert check_approval_mode(snapshot).status == "fail"


class TestReadAsTheRuntimeReadsIt:
    """Adversarial pass: the doctor must agree with the runtime on every spelling it accepts."""

    @pytest.mark.parametrize(("value", "status"), [(1, "pass"), (0, "fail"), (1.0, "fail")])
    def test_a_number_in_the_config_is_read_as_its_text(
        self, make_snapshot: MakeSnapshot, value: object, status: str
    ) -> None:
        """The runtime renders a TOML scalar with ``str`` (``1`` -> ``"1"``, truthy)."""
        snapshot = _with_baseline(make_snapshot, narrativetrace_config={"approval": value})
        assert check_approval_mode(snapshot).status == status

    @pytest.mark.parametrize(
        "text",
        [
            "def f(monkeypatch):\n"
            "    monkeypatch.setenv(name='NARRATIVETRACE_APPROVAL', value='1')\n",
            "import os\nos.environ['NARRATIVETRACE_APPROVAL'] = f'true'\n",
        ],
    )
    def test_keyword_arguments_and_constant_f_strings_switch_it_on(
        self, make_snapshot: MakeSnapshot, text: str
    ) -> None:
        snapshot = _with_baseline(make_snapshot, source_files={"conftest.py": text})
        assert check_approval_mode(snapshot).status == "pass"

    def test_an_f_string_with_a_placeholder_is_not_a_constant(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        text = "import os\nflag = 'true'\nos.environ['NARRATIVETRACE_APPROVAL'] = f'{flag}'\n"
        snapshot = _with_baseline(make_snapshot, source_files={"conftest.py": text})
        assert check_approval_mode(snapshot).status == "fail"

    @pytest.mark.parametrize(
        "line",
        [
            "NARRATIVETRACE_APPROVAL=true ; comment",
            "NARRATIVETRACE_APPROVAL=true # comment",
            "NARRATIVETRACE_APPROVAL=true,other",
        ],
    )
    def test_a_value_followed_by_more_text_is_not_the_switch(
        self, make_snapshot: MakeSnapshot, line: str
    ) -> None:
        """The runtime strips only whitespace: ``true ; comment`` is not truthy there."""
        ini = f"[pytest]\nenv =\n    {line}\n"
        snapshot = _with_baseline(make_snapshot, source_files={"pytest.ini": ini})
        assert check_approval_mode(snapshot).status == "fail"

    def test_an_inline_toml_table_entry_is_the_switch(self, make_snapshot: MakeSnapshot) -> None:
        text = 'env = { OTHER = "x", NARRATIVETRACE_APPROVAL = "true", MORE = "y" }\n'
        snapshot = _with_baseline(make_snapshot, source_files={"pyproject.toml": text})
        assert check_approval_mode(snapshot).status == "pass"
