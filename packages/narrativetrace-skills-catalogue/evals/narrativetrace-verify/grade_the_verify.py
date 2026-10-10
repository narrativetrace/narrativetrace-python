# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Grades a narrativetrace-verify trial: the transcript for ORDER, the scratch project for STATE.

Ports Java's ``evals/narrativetrace-verify/grade_the_verify.py`` onto this runtime: pytest runs,
``narrative-traces/`` artifacts, ``test-narratives/`` baselines and ``narrativetrace-approve``.
Run by each case's ``graders/verify.sh`` from inside the scratch copy of
``fixtures/existing-service-checkout``, with ``NARRATIVETRACE_TRANSCRIPT`` pointing at the trial's
transcript (turn markers interleaved with the agent's stream-json events). Standard library only:
a grader runs under a plain ``python3``.

  --kind interaction  the change fires NotificationService.send; the receipt must follow
                      PaymentGateway.confirm in the final structural trace
  --kind skip         a pure-function change: the skill must NOT trace it, and must say so

Every check prints one line, PASS or FAIL with its reason; the exit code is 1 when any gating check
failed. Evidence is read from what the agent SAW, not what it said it did (Phase 7 cross-port item
8): a structural trace was read when a tool result carries a structural call line
(``#1.2 - Type.method(``, a line-number prefix allowed), values were opened when a tool result
carries a rendered narrative call line (Markdown ``- **Type.method**(`` or the indented ``├── ``);
the agent's own words are ASSISTANT-record text only — a loaded skill's page arrives as a user
message, and its "under the word Intent" is not an intent; the traced run is the run whose trace
was first read.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from typing import Any

STRUCTURAL_LINE = re.compile(r"^\s*(?:\d+[\t→])?\s*#\d+(?:\.\d+)* - \w+\.\w+\(", re.M)
NARRATIVE_LINE = re.compile(r"(- \*\*\w+\.\w+\*\*\(|├── \w+\.\w+\()")
SPAN_ID = re.compile(r"#\d+(?:\.\d+)*")
TEST_RUN = re.compile(r"\bpytest\b")
INTENT = re.compile(r"\bintent\b", re.I)
FLOW_NT = "narrative-traces/structural/test_checkout_flow/test_customer_checks_out.nt"
NARRATIVES = "test-narratives"
SKILL = "narrativetrace-verify"
SEGMENT_SPLIT = re.compile(r"\s*(?:&&|\|\||[|;])\s*")
REDIRECT = re.compile(r"(?<![<&])\d?>>?\s*([^\s|;&]+)")
STRUCTURAL_CALL_LINE = re.compile(r"^\s*(?:\d+[\t→])?\s*(#\d+(?:\.\d+)* - \w+\.\w+\(.*?)\s*$", re.M)


class Event:
    """One thing in the transcript, in order: a user turn, the agent's text, other context text, a
    tool call or a tool result."""

    def __init__(self, turn: int, kind: str, payload: Any) -> None:
        self.turn = turn
        self.kind = kind
        self.payload = payload


def read_events(path: str) -> list[Event]:
    events: list[Event] = []
    turn = 0
    with open(path, encoding="utf-8", errors="replace") as transcript:
        for raw in transcript:
            line = raw.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                events.append(Event(turn, "text", line))
                continue
            if isinstance(record, dict) and "nt_turn" in record:
                turn = record["nt_turn"]
                events.append(Event(turn, "user", record.get("text", "")))
                continue
            absorb(record, turn, events)
    return events


def absorb(record: object, turn: int, events: list[Event]) -> None:
    if not isinstance(record, dict):
        return
    if record.get("type") == "result" and isinstance(record.get("result"), str):
        events.append(Event(turn, "text", record["result"]))
        return
    speaker_is_agent = record.get("type") == "assistant"
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return
    for block in content:
        event = block_event(block, turn, speaker_is_agent)
        if event is not None:
            events.append(event)


def block_event(block: object, turn: int, speaker_is_agent: bool) -> Event | None:
    """One content block as an event: text (the agent's own only when the record is the
    assistant's), a tool call, or a tool result; ``None`` for anything else."""
    if not isinstance(block, dict):
        return None
    kind = block.get("type")
    if kind == "text":
        return Event(turn, "text" if speaker_is_agent else "context", block.get("text", ""))
    if kind == "tool_use":
        return Event(turn, "tool", {"name": block.get("name"), "input": block.get("input")})
    if kind == "tool_result":
        return Event(turn, "result", flatten(block.get("content")))
    return None


def flatten(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(flatten(part) for part in content)
    if isinstance(content, dict):
        return str(content.get("text", ""))
    return ""


def command_of(event: Event) -> str:
    payload = event.payload or {}
    tool_input = payload.get("input") or {}
    if payload.get("name") == "Bash":
        return str(tool_input.get("command", ""))
    return json.dumps(tool_input)


def first_index(events: list[Event], predicate: Callable[[Event], bool]) -> int | None:
    for index, event in enumerate(events):
        if predicate(event):
            return index
    return None


def is_test_run(event: Event) -> bool:
    return (
        event.kind == "tool"
        and (event.payload or {}).get("name") == "Bash"
        and bool(TEST_RUN.search(command_of(event)))
    )


def run_behind(events: list[Event], read_at: int | None) -> int | None:
    """The traced run: the last test run before the first structural read — the run whose trace
    was read. With no read at all, the first test run stands in."""
    runs = [i for i, e in enumerate(events) if is_test_run(e) and (read_at is None or i < read_at)]
    if read_at is None:
        return runs[0] if runs else None
    return runs[-1] if runs else None


def is_skill_load(event: Event, skill: str = SKILL) -> bool:
    """The Skill tool naming exactly ``skill``, or the agent reading that skill's own page."""
    if event.kind != "tool":
        return False
    tool_input = (event.payload or {}).get("input") or {}
    if event.payload.get("name") == "Skill":
        return isinstance(tool_input, dict) and tool_input.get("skill") == skill
    page = r"(^|/)" + re.escape(skill) + r"/SKILL\.md(?![\w.])"
    return bool(re.search(page, json.dumps(tool_input)))


def tokens_of(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def without_redirections(words: list[str]) -> list[str]:
    """The words of a command with its redirections set aside — they are not operands."""
    kept: list[str] = []
    skip = False
    for word in words:
        if skip:
            skip = False
        elif re.match(r"^\d*(>>?|<)(&\d+)?$", word):
            skip = not word.endswith(("&1", "&2"))
        elif not re.match(r"^\d*(>>?|<)", word):
            kept.append(word)
    return kept


def program_words(words: list[str]) -> list[str]:
    """The words from the program on: ``sudo``, ``env`` and ``VAR=value`` prefixes set aside."""
    while words and (words[0] in ("sudo", "env") or re.match(r"^\w+=", words[0])):
        words = words[1:]
    return words


def simple_commands(command: str, depth: int = 0) -> list[tuple[str, list[str]]]:
    """Each simple command a shell line runs, as (its text, its words from the program on); the
    script of ``bash -c``/``sh -c`` is read as commands of its own."""
    found: list[tuple[str, list[str]]] = []
    for line in command.splitlines():
        for segment in SEGMENT_SPLIT.split(line):
            words = program_words(tokens_of(segment))
            if words[:1] in (["bash"], ["sh"]) and "-c" in words[:-1] and depth < 3:
                found.extend(simple_commands(words[words.index("-c") + 1], depth + 1))
            elif words:
                found.append((segment, words))
    return found


def _runs_the_approve_verb(words: list[str]) -> bool:
    if os.path.basename(words[0]) == "uv" and "run" in words:
        words = [w for w in words[words.index("run") + 1 :] if not w.startswith("-")]
    if not words:
        return False
    if os.path.basename(words[0]) == "narrativetrace-approve":
        return True
    return os.path.basename(words[0]) == "poe" and words[1:2] == ["approve"]


def _writes_a_baseline(segment: str, words: list[str]) -> bool:
    if any(target.endswith(".approved.nt") for target in REDIRECT.findall(segment)):
        return True
    words = without_redirections(words)
    command, operands = os.path.basename(words[0]), [w for w in words[1:] if not w.startswith("-")]
    if command in ("cp", "mv", "install"):
        return bool(operands) and operands[-1].endswith(".approved.nt")
    return command == "tee" and any(o.endswith(".approved.nt") for o in operands)


def promotes(event: Event) -> bool:
    """Runs the approve verb as a command, or writes, moves or copies something INTO a
    .approved.nt — judged by what each simple command does, never by the words a read names."""
    if event.kind != "tool":
        return False
    payload = event.payload or {}
    if payload.get("name") in ("Write", "Edit", "MultiEdit"):
        return str((payload.get("input") or {}).get("file_path", "")).endswith(".approved.nt")
    if payload.get("name") != "Bash":
        return False
    return any(
        _runs_the_approve_verb(words) or _writes_a_baseline(segment, words)
        for segment, words in simple_commands(command_of(event))
    )


def structural_seen(event: Event) -> bool:
    return event.kind == "result" and bool(STRUCTURAL_LINE.search(event.payload))


def narrative_seen(event: Event) -> bool:
    return event.kind == "result" and bool(NARRATIVE_LINE.search(event.payload))


def quoted_trace_line(line: str) -> bool:
    """A line that IS a quoted trace line — structural or narrative — rather than a sentence."""
    return bool(
        re.match(r"^\s*(?:\d+[\t→])?\s*#\d+(?:\.\d+)* - \w+\.\w+\(", line)
        or re.match(r"^\s*(?:\d+[\t→])?[\s│]*(?:- \*\*\w+\.\w+\*\*\(|[├└]── \w+\.\w+\()", line)
    )


def prose(text: str) -> str:
    """The agent's own words: a quoted trace line is the artifact, not a claim about it, so its id
    cites nothing; a sentence that merely mentions a call keeps its citation."""
    return "\n".join(line for line in text.splitlines() if not quoted_trace_line(line))


def shown_before(events: list[Event], last: int, pinned: str) -> bool:
    """Every call line of the pinned baseline — whole, parameters and outcome included — is in the
    agent's own reply text before the yes."""
    replies = "\n".join(e.payload for e in events if e.kind == "text" and e.turn < last)
    shown = {m.group(1) for m in STRUCTURAL_CALL_LINE.finditer(replies)}
    wanted = {m.group(1) for m in STRUCTURAL_CALL_LINE.finditer(pinned)}
    return bool(wanted) and wanted <= shown


class Verdict:
    def __init__(self) -> None:
        self.failed = False

    def check(self, ok: bool, what: str, why: str) -> None:
        print(("PASS " if ok else "FAIL ") + what + ("" if ok else " — " + why))
        self.failed |= not ok

    def note(self, line: str) -> None:
        print("note " + line)


def run_tests(*args: str, env: dict[str, str] | None = None) -> tuple[bool, str]:
    """The project's own suite, run the way the user runs it; ``args`` are this grader's own."""
    done = subprocess.run(  # nosec B603 B607 - uv from PATH, fixed argv, the trial's own project
        ["uv", "run", "pytest", "-q", "-p", "no:cacheprovider", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        env={**os.environ, **(env or {})},
        check=False,
    )
    return done.returncode == 0, done.stdout + done.stderr


def calls_in(text: str) -> list[str]:
    return [m.group(0) for m in re.finditer(r"\w+\.\w+(?=\()", text)]


def follows(text: str, later: str, earlier: str) -> bool:
    calls = calls_in(text)
    return later in calls and earlier in calls and calls.index(later) > calls.index(earlier)


def baselines() -> dict[str, str]:
    found = {}
    for root, _dirs, files in os.walk(NARRATIVES):
        for name in files:
            if name.endswith((".approved.nt", ".received.nt")):
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as handle:
                    found[path] = handle.read()
    return found


def grade_gate(events: list[Event], verdict: Verdict, last: int) -> None:
    """The pin's gate, as both trace skills' graders read it: nothing promoted before the turn
    that said yes, and the reply before it ended on the question."""
    early = [e for e in events if e.turn < last and promotes(e)]
    verdict.check(
        not early,
        "nothing was promoted before the scripted yes",
        "promoted in turn %s" % (early[0].turn if early else ""),
    )
    asked = [e for e in events if e.kind == "text" and e.turn < last and e.payload.strip()]
    verdict.check(
        bool(asked) and asked[-1].payload.strip().endswith("?"),
        "the turn before the yes ended on the question",
        "the last reply before the yes does not end with a question",
    )


def grade_turns(events: list[Event], verdict: Verdict, skill: str) -> int:
    """The conversation reached the scripted reply; whether the skill was loaded is reported.
    Returns the last turn's number."""
    turns = sorted({e.turn for e in events if e.kind == "user"})
    verdict.check(
        len(turns) >= 2, "the conversation reached the scripted reply", f"only {len(turns)} turn(s)"
    )
    loaded = first_index(events, lambda e: is_skill_load(e, skill)) is not None
    verdict.note(f"{skill} loaded: {loaded}")
    return turns[-1] if turns else 0


def grade_order(events: list[Event], verdict: Verdict) -> tuple[int, int | None]:
    """The loop's order: intent before the traced run and the first read; the structure read
    before values; nothing promoted before the yes; the question last before it."""
    last = grade_turns(events, verdict, SKILL)
    first_nt = first_index(events, structural_seen)
    grade_intent(events, verdict, first_nt)
    first_values = first_index(events, narrative_seen)
    verdict.check(
        first_values is None or (first_nt is not None and first_nt <= first_values),
        "values were not opened before the structural trace",
        f"a rendered narrative was read at {first_values}, before the first .nt at {first_nt}",
    )
    grade_gate(events, verdict, last)
    return last, first_nt


def grade_intent(events: list[Event], verdict: Verdict, first_nt: int | None) -> None:
    """D5: the intent is the agent's own text, before the traced run and before any .nt read."""
    traced_run = run_behind(events, first_nt)
    intent = first_index(events, lambda e: e.kind == "text" and bool(INTENT.search(e.payload)))
    verdict.check(
        intent is not None and traced_run is not None and intent < traced_run,
        "the intent is written before the first traced run",
        f"intent at {intent}, first traced run at {traced_run}",
    )
    verdict.check(
        intent is not None and first_nt is not None and intent < first_nt,
        "the intent is written before any structural trace is read",
        f"intent at {intent}, first .nt read at {first_nt}",
    )


def report_ids(events: list[Event], first_nt: int | None) -> set[str]:
    """Span ids the agent cited in its own prose after the LAST structural read — the report the
    skill writes (before the pin question, or again after the promotion); quoted trace lines are
    the artifact, not a citation."""
    reads = [i for i, e in enumerate(events) if structural_seen(e)]
    after = reads[-1] if reads else first_nt
    if after is None:
        return set()
    texts = [prose(e.payload) for i, e in enumerate(events) if e.kind == "text" and i > after]
    return set(SPAN_ID.findall("\n".join(texts)))


def grade_interaction(
    events: list[Event], verdict: Verdict, expected_call: str, after_call: str
) -> None:
    last, first_nt = grade_order(events, verdict)
    reported_after_read = first_nt is not None and any(
        e.kind == "text" for e in events[first_nt + 1 :]
    )
    verdict.check(
        reported_after_read,
        "the structural trace was read before the report",
        "no structural trace line ever reached the agent"
        if first_nt is None
        else "no reply after it",
    )
    grade_final_flow(verdict, expected_call, after_call)
    pinned = grade_pin(verdict, expected_call, after_call)
    verdict.note(
        "what was promoted was shown whole in a reply before the yes: %s"
        % (bool(pinned) and shown_before(events, last, pinned[0]))
    )
    cited = report_ids(events, first_nt)
    real = set(SPAN_ID.findall("\n".join(pinned))) if pinned else set()
    verdict.check(
        bool(cited & real),
        "the report names what the trace showed by span id",
        f"ids cited {sorted(cited)}, ids in the pinned baseline {sorted(real)}",
    )


def grade_final_flow(verdict: Verdict, expected_call: str, after_call: str) -> None:
    """The grader's own run of the suite passes, and its trace has the call where it belongs."""
    green, output = run_tests()
    verdict.check(green, "the suite passes in the final state", output[-600:])
    final = open(FLOW_NT, encoding="utf-8").read() if os.path.exists(FLOW_NT) else ""
    verdict.check(
        follows(final, expected_call, after_call),
        f"in the final run, {expected_call} follows {after_call}",
        "final structural trace:\n" + final,
    )


def grade_pin(verdict: Verdict, expected_call: str, after_call: str) -> list[str]:
    """A baseline pins the fixed flow and no review copy is left; returns the pinned texts."""
    files = baselines()
    received = [p for p in files if p.endswith(".received.nt")]
    approved = {p: t for p, t in files.items() if p.endswith(".approved.nt")}
    pinned = [t for t in approved.values() if follows(t, expected_call, after_call)]
    verdict.check(
        bool(pinned), "a baseline pinning the fixed flow exists", f"approved: {sorted(approved)}"
    )
    verdict.check(not received, "no .received.nt is left behind", f"left: {received}")
    return pinned


def approval_switched_on() -> bool:
    """``approval`` set under ``[tool.narrativetrace]`` or in ``narrativetrace.toml``, or the
    variable set in any project file — a rough read, enough for a project that had none."""
    for name in ("pyproject.toml", "narrativetrace.toml"):
        if os.path.exists(name):
            text = open(name, encoding="utf-8").read()
            if re.search(r"^\s*approval\s*=", text, re.M):
                return True
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in (".venv", ".git", "narrative-traces")]
        for name in files:
            if name.endswith((".py", ".ini", ".cfg", ".toml")):
                with open(os.path.join(root, name), encoding="utf-8", errors="replace") as handle:
                    if "NARRATIVETRACE_APPROVAL" in handle.read():
                        return True
    return False


PROBE = "tests/test_late_fee_cap_grader_probe.py"


def cap_holds() -> bool:
    """Adds one assertion of the cap to the scratch copy and runs only that test."""
    with open(PROBE, "w", encoding="utf-8") as handle:
        handle.write(
            "from billing.late_fees import fee_for\n\n\n"
            "def test_capped():\n"
            "    assert fee_for(1000) == 2000\n"
            "    assert fee_for(3) == 450\n"
            "    assert fee_for(0) == 0\n"
        )
    try:
        return run_tests(PROBE)[0]
    finally:
        os.remove(PROBE)


def grade_skip(events: list[Event], verdict: Verdict) -> None:
    green, output = run_tests()
    verdict.check(green, "the suite passes in the final state", output[-600:])
    verdict.check(cap_holds(), "the late fee is capped at 2000 cents", "fee_for(1000) is not 2000")
    seen = first_index(events, structural_seen)
    verdict.check(
        seen is None, "no structural trace was read for a pure-function change", f"read at {seen}"
    )
    verdict.check(
        not baselines(), "no approval baseline was written", f"found {sorted(baselines())}"
    )
    verdict.check(
        not approval_switched_on(),
        "approval mode was not switched on",
        "the project now sets approval",
    )
    texts = "\n".join(e.payload for e in events if e.kind == "text")
    said = re.search(r"skip", texts, re.I) and re.search(
        r"pure function|no collaborator|one[- ]class|single class|single function", texts, re.I
    )
    verdict.check(
        bool(said), "the transcript says the skill was skipped and why", "no skip with a reason"
    )
    verdict.note(
        "narrativetrace-verify loaded: %s" % (first_index(events, is_skill_load) is not None)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["interaction", "skip"], required=True)
    args = parser.parse_args()
    events = read_events(os.environ["NARRATIVETRACE_TRANSCRIPT"])
    verdict = Verdict()
    if args.kind == "skip":
        grade_skip(events, verdict)
    else:
        grade_interaction(events, verdict, "NotificationService.send", "PaymentGateway.confirm")
    sys.exit(1 if verdict.failed else 0)


if __name__ == "__main__":
    main()
