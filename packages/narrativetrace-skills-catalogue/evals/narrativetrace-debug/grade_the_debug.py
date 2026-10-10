# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Grades a narrativetrace-debug trial: the transcript for ORDER, the scratch project for STATE.

Ports Java's ``evals/narrativetrace-debug/grade_the_debug.py`` onto this runtime. Run by the
case's ``graders/verify.sh`` from inside the scratch copy of
``fixtures/existing-service-checkout-currency``, with ``NARRATIVETRACE_TRANSCRIPT`` pointing at
the trial's transcript. The transcript reading is the verify grader's own, imported rather than
copied: both read the same stream-json with the same rules (assistant-record text only, numbered
reads allowed, evidence from what the agent SAW).

The fixture's defect is a rounding in ``RateTableConverter.convert`` — it rounds to whole francs
before moving to cents — so 45.99 EUR at 0.93 is charged CHF 43.00, not 42.77. It is visible only as
a value: ``#1.3 RateTableConverter.convert(euro_cents: 4599, currency: "CHF") → 4300`` with its
child ``rate_for`` returning the right 0.93. The structural trace is the same before and after the
fix.

Every check prints one line, PASS or FAIL with its reason; the exit code is 1 when any gating check
failed. ``tests/test_trace_skill_graders.py`` holds the pure functions to the probes Java's
``check_grade_the_debug.py`` runs (cross-port item 5 of milestone 2).
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "narrativetrace-verify")
)
import grade_the_verify as gv

SKILL = "narrativetrace-debug"
DIVERGING_CALL = "RateTableConverter.convert"
PRODUCTION = "src/billing"
CONVERTER = PRODUCTION + "/rate_table_converter.py"
FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "fixtures",
    "existing-service-checkout-currency",
)
TRACES = "narrative-traces/traces"
MD_CALL = re.compile(r"\*\*(\w+\.\w+)\*\*\((.*)$")
STRUCTURAL_CALL = re.compile(r"^\s*(?:\d+[\t→])?\s*(#\d+(?:\.\d+)*) - (\w+\.\w+)\(")
NARRATIVE_CALL = re.compile(
    r"^\s*(?:\d+[\t→])?[\s│]*(?:- \*\*(\w+\.\w+)\*\*\(|[├└]── (\w+\.\w+)\()"
)
TRAILING_ID = re.compile(r"(#\d+(?:\.\d+)*)\s*$")
PARAMETER = re.compile(r"(?:^|`, )(\w+): `")
IN_PLACE = re.compile(r"^(-[a-zA-Z]*i[\w.]*|--in-place\S*)$")


def call_and_id(line: str) -> tuple[str, str] | None:
    """(call, own id) of one trace line, or None when the line is not a call line. Structural:
    the leading id; narrative (Markdown or the indented tree): the first call on the line and the
    line's own trailing id — never a call or an id quoted inside a value."""
    structural = STRUCTURAL_CALL.match(line)
    if structural:
        return structural.group(2), structural.group(1)
    narrative = NARRATIVE_CALL.match(line)
    trailing = TRAILING_ID.search(line)
    if narrative and trailing:
        return narrative.group(1) or narrative.group(2), trailing.group(1)
    return None


def diverging_ids(events: list[gv.Event]) -> set[str]:
    """The ids the agent was SHOWN for the diverging call, in any flavour."""
    ids: set[str] = set()
    for event in events:
        if event.kind != "result":
            continue
        for line in event.payload.splitlines():
            found = call_and_id(line)
            if found and found[0] == DIVERGING_CALL:
                ids.add(found[1])
    return ids


def in_production(path: str, cwd_in_production: bool = False) -> bool:
    """A path under src/billing — after resolving '..' — or a relative path written from inside
    it."""
    if not path or path.startswith(("-", "&")) or path == "/dev/null":
        return False
    norm = os.path.normpath(path.strip("'\"")).replace("\\", "/")
    under = bool(re.search(r"(^|/)" + PRODUCTION + r"(/|$)", norm))
    return under or (cwd_in_production and not norm.startswith("/"))


def segment_writes(segment: str, words: list[str], cwd_in_production: bool) -> bool:
    """One simple command writes production source: a redirect into it, an in-place sed/perl, tee,
    the destination of cp/mv/install, git checkout/restore of a path in it, or a script opening
    it for writing."""
    if any(in_production(t, cwd_in_production) for t in gv.REDIRECT.findall(segment)):
        return True
    words = gv.without_redirections(words)
    if not words:
        return False
    command, args = os.path.basename(words[0]), words[1:]
    if command.startswith("python") or command == "uv":
        return _script_writes_production(segment)
    targets = _write_targets(command, args)
    return any(in_production(target, cwd_in_production) for target in targets)


def _write_targets(command: str, args: list[str]) -> list[str]:
    """The paths a simple command writes: an in-place sed/perl's files, tee's operands, the
    destination of cp/mv/install, the paths git checkout/restore puts back."""
    targets = _TARGETS_OF.get(command)
    return targets(args) if targets is not None else []


def _operands(args: list[str]) -> list[str]:
    return [a for a in args if not a.startswith("-")]


def _in_place_files(args: list[str]) -> list[str]:
    if not any(IN_PLACE.match(a) for a in args):
        return []
    operands = _operands(args)
    return operands if "-e" in args or "-f" in args else operands[1:]


def _script_writes_production(segment: str) -> bool:
    opens = re.search(r"open\([^)]*" + PRODUCTION + r"/[^)]*['\"][wa]", segment)
    return bool(opens) or ("write_text" in segment and PRODUCTION in segment)


def _git_restored_paths(args: list[str]) -> list[str]:
    """The paths of ``git [-C dir] [-c k=v] checkout|restore ... <paths>``."""
    while len(args) >= 2 and args[0] in ("-C", "-c"):
        args = args[2:]
    if args[:1] not in (["checkout"], ["restore"]):
        return []
    return [a for a in args[1:] if not a.startswith("-")]


_TARGETS_OF = {
    "sed": _in_place_files,
    "perl": _in_place_files,
    "tee": _operands,
    "cp": lambda args: _operands(args)[-1:],
    "mv": lambda args: _operands(args)[-1:],
    "install": lambda args: _operands(args)[-1:],
    "git": _git_restored_paths,
}


def shell_writes_production(command: str) -> bool:
    """Walks a shell command's simple commands in order (``bash -c`` scripts and ``env``
    prefixes unwrapped by the shared reader), tracking a ``cd`` into production."""
    cwd_in_production = False
    for segment, words in gv.simple_commands(command):
        if words[:1] == ["cd"]:
            cwd_in_production = len(words) > 1 and in_production(words[1])
        elif segment_writes(segment, words, cwd_in_production):
            return True
    return False


def edits_production(event: gv.Event) -> bool:
    """A tool call that changes production source: an edit or write under src/billing, or a
    shell command whose write TARGET is there. A command that only names the path is a read."""
    if event.kind != "tool":
        return False
    payload = event.payload or {}
    tool_input = payload.get("input") or {}
    if payload.get("name") in ("Edit", "Write", "MultiEdit"):
        return in_production(str(tool_input.get("file_path", "")))
    return payload.get("name") == "Bash" and shell_writes_production(gv.command_of(event))


def prose(text: str) -> str:
    """The agent's own words, quoted trace lines set aside (a line whose own call and id parse)."""
    return "\n".join(line for line in text.splitlines() if call_and_id(line) is None)


def is_skill_load(event: gv.Event) -> bool:
    return gv.is_skill_load(event, SKILL)


def grade_order(events: list[gv.Event], verdict: gv.Verdict) -> None:
    last = gv.grade_turns(events, verdict, SKILL)
    fix_at = gv.first_index(events, edits_production)
    ids = diverging_ids(events)
    grade_read_before_fix(events, verdict, fix_at, ids)
    gv.grade_gate(events, verdict, last)
    grade_report(events, verdict, fix_at, ids, last)


def grade_read_before_fix(
    events: list[gv.Event], verdict: gv.Verdict, fix_at: int | None, ids: set[str]
) -> None:
    """The values were read, and the diverging span — an id the agent was SHOWN — named in its
    own words, before the first change to production code."""
    seen_first = diverging_ids(events[:fix_at]) if fix_at is not None else ids
    values_at = gv.first_index(events, gv.narrative_seen)
    verdict.check(
        values_at is not None and (fix_at is None or values_at < fix_at),
        "the values of the reproduction were read before the fix",
        "no rendered narrative reached the agent"
        if values_at is None
        else f"read at {values_at}, fix at {fix_at}",
    )
    named_at = gv.first_index(
        events,
        lambda e: e.kind == "text" and bool(seen_first & set(gv.SPAN_ID.findall(prose(e.payload)))),
    )
    verdict.check(
        bool(seen_first) and named_at is not None and fix_at is not None and named_at < fix_at,
        "the diverging span is named by its id before the fix",
        f"ids the agent saw for {DIVERGING_CALL} before the fix: {sorted(seen_first)}; "
        f"first named at {named_at}; first production edit at {fix_at}",
    )


def grade_report(
    events: list[gv.Event], verdict: gv.Verdict, fix_at: int | None, ids: set[str], last: int
) -> None:
    """The root cause by span id in the agent's prose after the fix (the gate puts the report
    before the pin question), and — reported — the id again in the closing reply."""
    after_fix = [
        e for i, e in enumerate(events) if e.kind == "text" and fix_at is not None and i > fix_at
    ]
    cited = set(gv.SPAN_ID.findall("\n".join(prose(e.payload) for e in after_fix)))
    verdict.check(
        bool(cited & ids),
        "the root-cause report after the fix names the diverging span by its id",
        f"ids cited after the fix {sorted(cited)}, ids of {DIVERGING_CALL} {sorted(ids)}",
    )
    closing = "\n".join(prose(e.payload) for e in events if e.kind == "text" and e.turn == last)
    again = bool(set(gv.SPAN_ID.findall(closing)) & ids)
    verdict.note(f"the closing reply names the diverging span again: {again}")


PROBE = "tests/test_converter_grader_probe.py"


def converter_value_is_right() -> bool:
    """The value AT the diverging span, in the final code: today's converter, the ticket's input."""
    with open(PROBE, "w", encoding="utf-8") as handle:
        handle.write(
            "from billing.daily_rates import DailyRates\n"
            "from billing.rate_table_converter import RateTableConverter\n\n\n"
            "def test_ticket():\n"
            "    converter = RateTableConverter(DailyRates())\n"
            '    assert converter.convert(4599, "CHF") == 4277\n'
            '    assert converter.convert(10000, "CHF") == 9300\n'
            '    assert converter.convert(4500, "EUR") == 4500\n'
        )
    try:
        return gv.run_tests(PROBE)[0]
    finally:
        os.remove(PROBE)


def lines_of(path: str) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        return [line.rstrip() for line in handle.read().splitlines()]


def shape_of(line: str) -> str | None:
    """'#id Type.method(names)' of a narrative call line — its own trailing id, its parameter
    names in order — or None for any other line."""
    found = call_and_id(line)
    match = MD_CALL.search(line)
    if not found or not match:
        return None
    names = ", ".join(PARAMETER.findall(match.group(2)))
    return f"{found[1]} {found[0]}({names})"


def shapes(traces_root: str) -> dict[str, list[str]]:
    """Each scenario's call shape from its .md narrative — written on a red run too, where no .nt
    is (the .nt is the last green one)."""
    found: dict[str, list[str]] = {}
    for directory, _dirs, files in os.walk(traces_root):
        for name in files:
            if name.endswith(".md"):
                path = os.path.join(directory, name)
                key = os.path.relpath(path, traces_root)
                found[key] = [s for s in map(shape_of, lines_of(path)) if s]
    return found


def run_with_the_fixtures_production_code(output_dir: str) -> bool:
    """Runs the suite with every fixture production file put back as it shipped — in place, so the
    project's own environment (an editable install of this package) runs it — and the agent's
    files restored afterwards. Approval is off and the artifacts go to ``output_dir``, so neither
    the agent's baselines nor its last-green traces are touched."""
    fixture_main = os.path.join(FIXTURE, PRODUCTION)
    saved = tempfile.mkdtemp(prefix="debug-grader-agent-src-")
    shutil.copytree(PRODUCTION, saved, dirs_exist_ok=True)
    try:
        for directory, _dirs, files in os.walk(fixture_main):
            for name in files:
                source = os.path.join(directory, name)
                target = os.path.join(PRODUCTION, os.path.relpath(source, fixture_main))
                shutil.copyfile(source, target)
        env = {"NARRATIVETRACE_APPROVAL": "false", "NARRATIVETRACE_OUTPUT_DIR": output_dir}
        return gv.run_tests("--continue-on-collection-errors", env=env)[0]
    finally:
        shutil.rmtree(PRODUCTION)
        shutil.copytree(saved, PRODUCTION)
        shutil.rmtree(saved, ignore_errors=True)


def grade_state(verdict: gv.Verdict) -> None:
    green, output = gv.run_tests()
    verdict.check(green, "the suite passes in the final state", output[-600:])
    changed = os.path.exists(CONVERTER) and lines_of(CONVERTER) != lines_of(
        os.path.join(FIXTURE, CONVERTER)
    )
    verdict.check(
        changed, "the fix touches the diverging span's code", CONVERTER + " is as shipped"
    )
    verdict.check(
        converter_value_is_right(),
        "the diverging span now carries the right value (4599 EUR at 0.93 is 4277)",
        "RateTableConverter still converts the ticket's input wrongly — silenced elsewhere",
    )
    after = shapes(TRACES)
    grade_baseline(verdict)
    output_dir = tempfile.mkdtemp(prefix="debug-grader-prefix-")
    try:
        reverted_green = run_with_the_fixtures_production_code(output_dir)
        verdict.check(
            not reverted_green,
            "a regression test fails when the fix is undone",
            "with the fixture's production code back, every test still passes",
        )
        before = shapes(os.path.join(output_dir, "traces"))
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)
    grade_delta(verdict, before, after)


def grade_delta(
    verdict: gv.Verdict, before: dict[str, list[str]], after: dict[str, list[str]]
) -> None:
    common = sorted(set(before) & set(after))
    reaching = [s for s in common if any(DIVERGING_CALL + "(" in line for line in before[s])]
    moved = [
        f"{s}:\n  before {before[s]}\n  after  {after[s]}" for s in common if before[s] != after[s]
    ]
    verdict.check(
        bool(reaching) and not moved,
        "the structural delta against the pre-fix run shows nothing else moved",
        f"no scenario reached {DIVERGING_CALL} in both runs" if not reaching else "\n".join(moved),
    )


def grade_baseline(verdict: gv.Verdict) -> None:
    files = gv.baselines()
    received = [p for p in files if p.endswith(".received.nt")]
    pinned = [
        p for p, t in files.items() if p.endswith(".approved.nt") and DIVERGING_CALL + "(" in t
    ]
    verdict.check(
        bool(pinned), "a baseline pinning the reproduced flow exists", f"found {sorted(files)}"
    )
    verdict.check(not received, "no .received.nt is left behind", f"left: {received}")


def main() -> None:
    events = gv.read_events(os.environ["NARRATIVETRACE_TRANSCRIPT"])
    verdict = gv.Verdict()
    grade_order(events, verdict)
    grade_state(verdict)
    sys.exit(1 if verdict.failed else 0)


if __name__ == "__main__":
    main()
