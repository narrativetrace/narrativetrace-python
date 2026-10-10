# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The ``narrativetrace-debug`` grader, rehearsed BEFORE any trial is spent.

Two layers. The pure functions are held to the probes Java's ``check_grade_the_debug.py`` runs
(Phase 7 milestone 2, cross-port item 5) — reads are not fixes, every write form is a write, a
trace line's call and id come from its own position, never a value — on this port's production
path, ``src/billing``. Then real project states, built through the real pytest plugin and approve
verb: a solved trial, the untouched project and each near miss, asserting the grader's reason.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "narrativetrace-debug"))
sys.path.insert(0, str(_HERE / "narrativetrace-verify"))

import grade_the_debug as gd  # noqa: E402
import grade_the_verify as gv  # noqa: E402
from trace_skill_rehearsal import (  # noqa: E402
    Stream,
    patched_test_runner,
    pin,
    run_pytest,
    scaffold,
)

_SRC = "src/billing/rate_table_converter.py"
_CC = "RateTableConverter.convert"


def _bash(command: str) -> gv.Event:
    return gv.Event(1, "tool", {"name": "Bash", "input": {"command": command}})


def _tool(name: str, tool_input: object) -> gv.Event:
    return gv.Event(1, "tool", {"name": name, "input": tool_input})


def _result(text: str) -> gv.Event:
    return gv.Event(1, "result", text)


@pytest.mark.parametrize(
    "command",
    [
        f"sed -n '1,20p' {_SRC} 2>&1",
        f"cat {_SRC} > /tmp/copy.py",
        f"cat {_SRC} >/dev/null 2>&1",
        f"cp {_SRC} /tmp/backup.py",
        f"cp -n {_SRC} /tmp/a.py 2>&1",
        f"grep -n 'a>b' {_SRC}",
        f'grep -n "->" {_SRC}',
        f"ls > /tmp/list.txt && cat {_SRC}",
        "find src/billing -name '*.py' > /tmp/files.txt",
        f"diff {_SRC} /tmp/B.py > /tmp/d.txt",
        f'echo "see {_SRC}" > notes.txt',
        f"cat {_SRC} | tee /tmp/copy.txt",
        f"cat {_SRC}; echo done > /tmp/x",
        "echo x > src/billingx/x.py",
        "sed -i 's#src/billing/#gen/#' pyproject.toml",
        "grep -rn tee src/billing/",
        f"grep -n mv {_SRC}",
        'grep -rn "cp" src/billing/',
        "uv run pytest tests/test_checkout_flow.py",
    ],
)
def test_a_command_that_only_reads_production_is_not_a_fix(command: str) -> None:
    assert not gd.edits_production(_bash(command))


@pytest.mark.parametrize(
    "command",
    [
        "sed -i.bak 's/a/b/' src/billing/x.py",
        "sed --in-place 's/a/b/' src/billing/x.py",
        "sed -i 's/a/b/' \"src/billing/x.py\"",
        "sed -i 's/a/b/' 'src/billing/x.py'",
        "cat <<EOF > src/billing/x.py\nX = 1\nEOF",
        "cat <<'EOF' >\"src/billing/x.py\"\nX = 1\nEOF",
        "printf 'x' >> src/billing/x.py",
        "printf 'x'>>src/billing/x.py",
        "echo x | tee -a src/billing/x.py",
        "echo x | tee src/billing/x.py",
        "perl -pi -e 's/a/b/' src/billing/x.py",
        "cp /tmp/fixed.py src/billing/x.py",
        "mv /tmp/fixed.py src/billing/x.py",
        "cp /tmp/fixed.py 'src/billing/x.py'",
        "cp /tmp/fixed.py src/billing/x.py 2>&1",
        "sed -E -i 's/a/b/' src/billing/x.py",
        "cd src/billing && sed -i 's/a/b/' x.py",
        "git checkout -- src/billing/x.py",
        "python3 -c \"open('src/billing/x.py','w').write('x')\"",
        "uv run python -c \"open('src/billing/x.py','w').write('x')\"",
    ],
)
def test_every_form_of_write_to_production_is_a_fix(command: str) -> None:
    assert gd.edits_production(_bash(command))


class TestToolEdits:
    def test_edit_write_and_multi_edit_under_production_are_fixes(self) -> None:
        for name in ("Edit", "Write", "MultiEdit"):
            assert gd.edits_production(_tool(name, {"file_path": "/w/" + _SRC}))

    def test_a_dot_dot_segment_into_production_is_a_fix(self) -> None:
        assert gd.edits_production(_tool("Write", {"file_path": "/w/tests/../src/billing/x.py"}))

    @pytest.mark.parametrize(
        "event",
        [
            _tool("Read", {"file_path": "/w/" + _SRC}),
            _tool("Edit", {"file_path": "/w/src/billingx/x.py"}),
            _tool("Edit", {"file_path": "/w/tests/test_x.py"}),
            _tool("Bash", {}),
            _tool("Bash", None),
            _result("sed -i x src/billing/a.py"),
        ],
    )
    def test_reads_tests_siblings_and_results_are_not_fixes(self, event: gv.Event) -> None:
        assert not gd.edits_production(event)


class TestDivergingIds:
    def test_a_structural_line_names_its_own_span(self) -> None:
        line = f"#1.3 - {_CC}(euro_cents, currency) → value"
        assert gd.diverging_ids([_result(line)]) == {"#1.3"}

    def test_a_numbered_read_of_a_structural_line_counts(self) -> None:
        assert gd.diverging_ids([_result(f"     7\t  #1.3 - {_CC}(euro_cents, currency)")]) == {
            "#1.3"
        }

    def test_markdown_and_indented_lines_name_their_trailing_span(self) -> None:
        markdown = f'  - **{_CC}**(euro_cents: `4599`, currency: `"CHF"`) → `4300` #1.3'
        indented = f'├── {_CC}(euro_cents: 4599, currency: "CHF") → 4300 #1.3'
        assert gd.diverging_ids([_result(markdown), _result(indented)]) == {"#1.3"}

    @pytest.mark.parametrize(
        "line",
        [
            f"{_CC}(euro_cents: 1)",
            "#1.5 - RateTableConverter.convertAll(euro_cents)",
            "#1.5 - MyRateTableConverter.convert(euro_cents)",
            f'#1.2 - CheckoutService.checkout(note: "{_CC}") → value',
        ],
    )
    def test_near_misses_name_nothing(self, line: str) -> None:
        assert gd.diverging_ids([_result(line)]) == set()

    def test_agent_text_is_not_evidence_it_was_shown(self) -> None:
        assert gd.diverging_ids([gv.Event(1, "text", f"#1.3 - {_CC}(")]) == set()

    def test_an_id_inside_a_value_is_not_the_spans_own(self) -> None:
        assert gd.diverging_ids([_result(f'#1.3 - {_CC}(note: "see #9") → value')]) == {"#1.3"}


class TestProse:
    @pytest.mark.parametrize(
        "quoted",
        [
            "    12\t#1.3 - A.b(x)",
            "    12→#1.3 - A.b(x)",
            f"- **{_CC}**(euro_cents: `4599`) → `4300` #1.3",
            f"├── {_CC}(euro_cents: 4599) #1.3",
        ],
    )
    def test_a_quoted_trace_line_cites_nothing(self, quoted: str) -> None:
        assert "#1.3" not in gd.prose(quoted)

    def test_sentences_keep_their_citations(self) -> None:
        mixed = "The rounding happens at #1.3.\n    12\t#1.3 - A.b(x)\nand #1.3 is the cause"
        assert gd.prose(mixed).count("#1.3") == 2

    def test_a_claim_quoting_a_call_mid_sentence_keeps_its_citation(self) -> None:
        claim = f"Root cause at #1.3, where 4599 became 4300 near ├── {_CC}("
        assert "#1.3" in gd.prose(claim)


class TestShapeOf:
    @pytest.mark.parametrize(
        ("line", "shape"),
        [
            ("- **Order.place**(id: `42`, note: `ok`) → `done` #1.3", "#1.3 Order.place(id, note)"),
            (
                "- **Order.place**(id: `f(x)`, note: `ok`) → `done` #1.3",
                "#1.3 Order.place(id, note)",
            ),
            ("- **Order.place**(ref: `#2`, id: `42`) → `done` #1.3", "#1.3 Order.place(ref, id)"),
            ("- **Order.place**() → `ok` #1.3", "#1.3 Order.place()"),
            ("- **Order.place**(ref: `x: `, id: `42`) → `done` #1.3", "#1.3 Order.place(ref, id)"),
        ],
    )
    def test_a_narrative_call_line_gives_its_id_and_parameter_names(
        self, line: str, shape: str
    ) -> None:
        assert gd.shape_of(line) == shape

    @pytest.mark.parametrize(
        "line",
        ["- **Order.place**(ref: `#2`) → `done`", "Order.place(id: 42) #1.3", "plain text #1.3"],
    )
    def test_anything_else_has_no_shape(self, line: str) -> None:
        assert gd.shape_of(line) is None


class TestSkillLoad:
    def test_the_skill_tool_or_the_page_is_a_load(self) -> None:
        assert gd.is_skill_load(_tool("Skill", {"skill": "narrativetrace-debug"}))
        assert gd.is_skill_load(
            _tool("Read", {"file_path": "/w/.claude/skills/narrativetrace-debug/SKILL.md"})
        )
        assert gd.is_skill_load(_bash("cat /w/.agents/skills/narrativetrace-debug/SKILL.md"))

    @pytest.mark.parametrize(
        "event",
        [
            _tool("Read", {"file_path": "/w/.claude/skills/narrativetrace-verify/SKILL.md"}),
            _result("narrativetrace-debug/SKILL.md"),
            gv.Event(1, "text", "I will use narrativetrace-debug"),
            _tool("Skill", {"skill": "narrativetrace-debug-old"}),
            _tool("Skill", {"skill": "narrativetrace-verify", "args": "narrativetrace-debug"}),
        ],
    )
    def test_anything_else_is_not(self, event: gv.Event) -> None:
        assert not gd.is_skill_load(event)


# --- real project states -------------------------------------------------------------------------

_FIXTURE = "existing-service-checkout-currency"
_REPRODUCTION = """from narrativetrace import trace_object

from billing.checkout_service import CheckoutService
from billing.customer_directory import CustomerDirectory
from billing.daily_rates import DailyRates
from billing.invoice_service import InvoiceService
from billing.payment_gateway import PaymentGateway
from billing.rate_table_converter import RateTableConverter


def test_ticket_4471_a_franc_card_is_charged_the_exact_amount(narrative_trace):
    gateway = PaymentGateway()
    checkout = trace_object(
        CheckoutService(
            trace_object(InvoiceService(), narrative_trace),
            trace_object(CustomerDirectory({"C-2041": "CHF"}), narrative_trace),
            trace_object(
                RateTableConverter(trace_object(DailyRates(), narrative_trace)), narrative_trace
            ),
            trace_object(gateway, narrative_trace),
        ),
        narrative_trace,
    )
    checkout.checkout("C-2041", 4599, "card-visa-4242")
    assert gateway.captured == ["AUTH-card-visa-4242-4277-CHF"]
"""
_TICKET_MD = (
    "narrative-traces/traces/test_ticket_4471/"
    "test_ticket_4471_a_franc_card_is_charged_the_exact_amount.md"
)


def _reproduce(project: Path) -> str:
    (project / "tests" / "test_ticket_4471.py").write_text(_REPRODUCTION, encoding="utf-8")
    run_pytest(project)
    return (project / _TICKET_MD).read_text(encoding="utf-8")


def _fix_converter(project: Path) -> None:
    converter = project / _SRC
    text = converter.read_text(encoding="utf-8")
    converter.write_text(
        text.replace(
            "        whole_units = round(euro_cents / 100 * rate)\n"
            "        return whole_units * 100",
            "        return round(euro_cents * rate)",
        ),
        encoding="utf-8",
    )


def _transcript(seen: str, *, named_before_fix: bool = True, report: str = "#1.3") -> Stream:
    stream = Stream().user(1, "Support ticket 4471: ...")
    stream.tool("Skill", {"skill": "narrativetrace-debug"})
    stream.bash("uv run pytest tests/test_ticket_4471.py", "1 failed")
    stream.tool("Read", {"file_path": "/s/" + _TICKET_MD}, seen)
    if named_before_fix:
        stream.say("The value diverges at #1.3: 4599 went in at 0.93 and 4300 came out.")
    stream.tool("Edit", {"file_path": "/s/" + _SRC})
    if not named_before_fix:
        stream.say("Fixed; the value diverged at #1.3.")
    stream.bash("uv run pytest", "5 passed")
    stream.bash("uv run pytest || true", "2 failed")
    stream.say(f"Root cause at {report}: rounding to whole francs before cents. Pin it?")
    stream.user(2, "yes, pin it").bash("uv run narrativetrace-approve", "Approved")
    return stream.say(f"Pinned; the cause was at {report}.")


def _grade(project: Path, stream: Stream, monkeypatch: pytest.MonkeyPatch) -> set[str]:
    printed: list[str] = []
    transcript = stream.write_to(project.parent / "transcript.jsonl")
    monkeypatch.chdir(project)
    monkeypatch.setattr("builtins.print", printed.append)
    verdict = gv.Verdict()
    with patched_test_runner(gv, project):
        gd.grade_order(gv.read_events(str(transcript)), verdict)
        gd.grade_state(verdict)
    monkeypatch.undo()
    return {line.split(" — ")[0] for line in printed if line.startswith("FAIL")}


class TestDebugStates:
    def test_a_solved_trial_passes_every_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        seen = _reproduce(project)
        _fix_converter(project)
        pin(project)

        assert _grade(project, _transcript(seen), monkeypatch) == set()

    def test_the_untouched_project_fails_on_the_fix_the_regression_test_and_the_pin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)

        failed = _grade(
            project, Stream().user(1, "Support ticket 4471").say("No idea."), monkeypatch
        )

        assert {
            "FAIL the fix touches the diverging span's code",
            "FAIL the diverging span now carries the right value (4599 EUR at 0.93 is 4277)",
            "FAIL a regression test fails when the fix is undone",
            "FAIL a baseline pinning the reproduced flow exists",
        } <= failed

    def test_a_symptom_silenced_downstream(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        seen = _reproduce(project)
        checkout = project / "src" / "billing" / "checkout_service.py"
        checkout.write_text(
            checkout.read_text(encoding="utf-8").replace(
                "charged = self._converter.convert(invoice.euro_cents, currency)",
                "charged = self._converter.convert(invoice.euro_cents, currency)\n"
                '        if currency == "CHF":\n'
                "            charged = round(invoice.euro_cents * 0.93)",
            ),
            encoding="utf-8",
        )
        pin(project)

        failed = _grade(project, _transcript(seen), monkeypatch)

        assert {
            "FAIL the fix touches the diverging span's code",
            "FAIL the diverging span now carries the right value (4599 EUR at 0.93 is 4277)",
        } <= failed

    def test_a_fix_that_bypasses_the_converter_moves_the_shape(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        seen = _reproduce(project)
        _fix_converter(project)
        checkout = project / "src" / "billing" / "checkout_service.py"
        checkout.write_text(
            checkout.read_text(encoding="utf-8").replace(
                "charged = self._converter.convert(invoice.euro_cents, currency)",
                "charged = round(invoice.euro_cents * "
                '{"EUR": 1.0, "CHF": 0.93, "GBP": 0.85}[currency])',
            ),
            encoding="utf-8",
        )
        pin(project)

        failed = _grade(project, _transcript(seen), monkeypatch)

        assert (
            "FAIL the structural delta against the pre-fix run shows nothing else moved" in failed
        )

    def test_fixed_with_no_regression_test(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        seen = _reproduce(project)
        (project / "tests" / "test_ticket_4471.py").unlink()
        _fix_converter(project)
        pin(project)

        failed = _grade(project, _transcript(seen), monkeypatch)

        assert failed == {"FAIL a regression test fails when the fix is undone"}

    def test_fixed_before_the_span_was_named(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        seen = _reproduce(project)
        _fix_converter(project)
        pin(project)

        failed = _grade(project, _transcript(seen, named_before_fix=False), monkeypatch)

        assert failed == {"FAIL the diverging span is named by its id before the fix"}

    def test_a_report_without_the_id(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project = scaffold(_FIXTURE, tmp_path)
        seen = _reproduce(project)
        _fix_converter(project)
        pin(project)

        failed = _grade(project, _transcript(seen, report="the converter"), monkeypatch)

        assert failed == {
            "FAIL the root-cause report after the fix names the diverging span by its id"
        }


@pytest.mark.parametrize(
    "command",
    [
        "bash -c \"sed -i 's/a/b/' src/billing/x.py\"",
        "sh -c 'printf x > src/billing/x.py'",
        "env LANG=C sed -i 's/a/b/' src/billing/x.py",
        "git -C /repo checkout -- src/billing/x.py",
    ],
)
def test_a_write_wrapped_in_a_shell_env_or_git_option_is_still_a_fix(command: str) -> None:
    assert gd.edits_production(_bash(command))
