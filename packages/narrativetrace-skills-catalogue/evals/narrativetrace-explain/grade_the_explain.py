# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Grades a narrativetrace-explain trial: the transcript for ORDER, the scratch project for STATE.

Ports Java's ``evals/narrativetrace-explain/grade_the_explain.py`` onto this runtime. Run by each
case's ``graders/verify.sh`` from inside the scratch copy of ``fixtures/existing-service-checkout``,
with ``NARRATIVETRACE_TRANSCRIPT`` pointing at the trial's transcript. The transcript parsing is the
verify grader's own (``grade_the_verify``), imported rather than copied: both read the same
stream-json with the same rules (assistant-record text only, numbered reads allowed, evidence from
what the agent SAW).

  --kind explain  an unfamiliar flow: the skill ran, a trace was produced, and the answer cites a
                  span id that trace actually has
  --kind control  a pure function: nothing installed, nothing run, nothing traced, and the answer
                  comes from the source

The fixture's checkout flow is ``tests/test_checkout_flow.py::test_customer_checks_out`` driving
``CheckoutService.checkout``: it issues the invoice, authorizes the payment through shopkit's
``CheckoutFlow`` — which is not itself wrapped — fires the ``payment_succeeded`` hook, whose one
handler (``billing.compose``) records the payment on the ledger, and confirms the payment.
``NotificationService`` is handed in and never called, and shopkit's ``CheckoutFlow`` and ``Hooks``
have no span of their own. That is what an explanation of this flow has to get right, and none of
it is visible in the comments.

What GATES is mechanical: the skill was invoked, a trace exists, a structural trace reached the
agent before its answer, the answer cites an id that trace carries, and the production code was not
touched (the skill's own "never change the code in order to explain it"). What is REPORTED rather
than gated is judgment — whether the calls were named in order, whether the unobserved code was
named, whether values were opened — the same split ``evals/README.md``'s "What gates" table draws,
and the same one ``grade_the_verify`` uses for "what was promoted was shown whole".

Every check prints one line, PASS or FAIL with its reason; the exit code is 1 when any gating check
failed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterable

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "narrativetrace-verify")
)
import grade_the_verify as gv

SKILL = "narrativetrace-explain"
FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "fixtures", "existing-service-checkout"
)
TRACE_ROOT = "narrative-traces"
STRUCTURAL = os.path.join(TRACE_ROOT, "structural")
# Only the three directories a traced RUN writes. Scoped rather than walking narrative-traces whole,
# because the clarity report lands there too and a naming report is not a trace: counting it would
# make "nothing was traced" false for the control case the moment anything scanned.
TRACE_DIRECTORIES = (
    STRUCTURAL,
    os.path.join(TRACE_ROOT, "traces"),
    os.path.join(TRACE_ROOT, "diagrams"),
)
# pyproject.toml only: ``uv run`` writes a uv.lock the fixture does not carry, and that is a tool's
# side effect, not a dependency the agent added.
BUILD_FILES = ("pyproject.toml",)
# What running the interpreter's tests leaves in a source tree; not a change to the code.
BYTECODE = ("__pycache__", ".pyc")
# The flow's calls, in the order the run makes them — reported, never gated: whether a cheap model
# narrates them in order is a judgment measure, and the ordering claim is the product's promise
# rather than this harness's oracle.
FLOW_CALLS = [
    "InvoiceService.issue_invoice",
    "PaymentGateway.authorize",
    "LedgerService.record_paid",
    "PaymentGateway.confirm",
]
PROJECT_TOOLS = ("uv", "uvx", "pytest", "python", "python3")
NOT_OBSERVED = re.compile(r"not observ|unobserv|no span|not traced|untraced|not wrapped", re.I)
FROM_THE_SOURCE = re.compile(
    r"reading the source|from the source|pure function|no collaborator", re.I
)


def skill_invoked(events: list[gv.Event]) -> bool:
    """The Skill tool, naming this skill — what "the skill triggered" means mechanically."""
    for event in events:
        if event.kind == "tool" and (event.payload or {}).get("name") == "Skill":
            if SKILL in json.dumps(event.payload.get("input")):
                return True
    return False


def page_read(events: list[gv.Event]) -> int | None:
    """The agent opened the page itself instead of invoking it — a different observation."""
    return gv.first_index(
        events,
        lambda e: e.kind == "tool" and SKILL + "/SKILL.md" in json.dumps(e.payload.get("input")),
    )


def runs_the_project(event: gv.Event) -> bool:
    """A Bash call whose simple commands start the project's tooling — judged by the program a
    command runs, never by the word ``pytest`` appearing as an operand of a ``grep``."""
    if event.kind != "tool" or (event.payload or {}).get("name") != "Bash":
        return False
    return any(
        os.path.basename(words[0]) in PROJECT_TOOLS
        for _segment, words in gv.simple_commands(gv.command_of(event))
    )


def ran_the_project(events: list[gv.Event]) -> int | None:
    """The first index at which the agent ran the project's own tooling at all."""
    return gv.first_index(events, runs_the_project)


def trace_files() -> dict[str, str]:
    """Every trace the run left in the project, by path — the state of "a trace was produced"."""
    found = {}
    for directory in TRACE_DIRECTORIES:
        for root, _dirs, files in os.walk(directory):
            for name in files:
                if name.endswith((".nt", ".md", ".mmd", ".json")):
                    path = os.path.join(root, name)
                    with open(path, encoding="utf-8", errors="replace") as handle:
                        found[path] = handle.read()
    return found


def ids_in(texts: Iterable[str]) -> set[str]:
    ids: set[str] = set()
    for text in texts:
        ids.update(gv.SPAN_ID.findall(text))
    return ids


def final_answer(events: list[gv.Event]) -> str:
    """The agent's own text in the last turn — the explanation the user reads."""
    turns = sorted({e.turn for e in events if e.kind == "user"})
    last = turns[-1] if turns else 0
    return "\n".join(e.payload for e in events if e.kind == "text" and e.turn == last)


def read_bytes(path: str) -> bytes | None:
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as handle:
        return handle.read()


def is_bytecode(path: str) -> bool:
    return any(marker in path for marker in BYTECODE)


def changed_under(relative: str) -> list[str]:
    """Files under ``relative`` that differ from the fixture's own, plus any added or removed;
    interpreter bytecode is not a difference."""
    source = os.path.join(FIXTURE, relative)
    differences = []
    for root, _dirs, files in os.walk(source):
        for name in files:
            original = os.path.join(root, name)
            copied = os.path.join(relative, os.path.relpath(original, source))
            if not os.path.exists(copied) or read_bytes(copied) != read_bytes(original):
                differences.append(copied)
    for root, _dirs, files in os.walk(relative):
        for name in files:
            copied = os.path.join(root, name)
            original = os.path.join(source, os.path.relpath(copied, relative))
            if not os.path.exists(original):
                differences.append(copied)
    return sorted(path for path in set(differences) if not is_bytecode(path))


def changed_build_files() -> list[str]:
    return sorted(
        name for name in BUILD_FILES if read_bytes(name) != read_bytes(os.path.join(FIXTURE, name))
    )


def calls_named_in_order(answer: str) -> bool:
    """Whether the answer names at least two of the flow's calls, in the order the run made them."""
    positions = [(answer.find(call), call) for call in FLOW_CALLS]
    seen = [(at, call) for at, call in positions if at >= 0]
    return len(seen) >= 2 and seen == sorted(seen)


def last_text_index(events: list[gv.Event]) -> int | None:
    indexes = [i for i, e in enumerate(events) if e.kind == "text" and e.payload.strip()]
    return indexes[-1] if indexes else None


def grade_explain(events: list[gv.Event], verdict: gv.Verdict) -> None:
    verdict.check(skill_invoked(events), "the Skill tool invoked " + SKILL, "it never did")
    verdict.note("the page was read rather than invoked: %s" % (page_read(events) is not None))

    traces = trace_files()
    structural = {p: t for p, t in traces.items() if p.endswith(".nt")}
    verdict.check(
        bool(structural),
        "the run left a structural trace in the project",
        f"nothing under {STRUCTURAL} — found {sorted(traces)}",
    )

    first_nt = gv.first_index(events, gv.structural_seen)
    answer_at = last_text_index(events)
    verdict.check(
        first_nt is not None and answer_at is not None and first_nt < answer_at,
        "a structural trace reached the agent before its answer",
        "no structural trace line ever reached the agent"
        if first_nt is None
        else f"read at {first_nt}, after the answer at {answer_at}",
    )

    answer = final_answer(events)
    cited = ids_in([answer])
    real = ids_in(structural.values()) or ids_in(traces.values())
    verdict.check(
        bool(cited & real),
        "the answer cites a span id the trace it produced actually has",
        f"ids cited {sorted(cited)}, ids in the trace {sorted(real)}",
    )

    verdict.check(
        not changed_under("src") and not changed_build_files(),
        "the production code and the build were left alone",
        "changed: {} {}".format(changed_under("src"), changed_build_files()),
    )
    report_the_judgment(events, verdict, answer)


def report_the_judgment(events: list[gv.Event], verdict: gv.Verdict, answer: str) -> None:
    verdict.note(
        f"the flow's calls are named in the order they ran: {calls_named_in_order(answer)}"
    )
    verdict.note(f"the answer names what was not observed: {bool(NOT_OBSERVED.search(answer))}")
    verdict.note("values were opened: %s" % (gv.first_index(events, gv.narrative_seen) is not None))
    verdict.note("the scenario's own sources changed: {}".format(changed_under("tests")))


def grade_control(events: list[gv.Event], verdict: gv.Verdict) -> None:
    verdict.check(
        not changed_build_files(),
        "no dependency was added and no build file changed",
        f"changed: {changed_build_files()}",
    )
    verdict.check(
        not changed_under("src") and not changed_under("tests"),
        "the project's sources were left alone",
        "changed: {} {}".format(changed_under("src"), changed_under("tests")),
    )
    at = ran_the_project(events)
    verdict.check(at is None, "nothing was run", f"the project's tooling ran at event {at}")
    traces = trace_files()
    seen = gv.first_index(events, lambda e: gv.structural_seen(e) or gv.narrative_seen(e))
    verdict.check(
        not traces and seen is None,
        "nothing was traced",
        f"traces on disk {sorted(traces)}, a trace line reached the agent at {seen}",
    )

    answer = final_answer(events)
    verdict.check(
        "fee_for" in answer and "150" in answer and bool(re.search(r"\b(zero|0)\b", answer)),
        "the answer comes from the source: the function, the rate and the not-late case",
        "answer:\n" + answer[-800:],
    )
    verdict.note(f"the skill was invoked: {skill_invoked(events)}")
    verdict.note(f"the reply says why it is not tracing: {bool(FROM_THE_SOURCE.search(answer))}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["explain", "control"], required=True)
    args = parser.parse_args()
    events = gv.read_events(os.environ["NARRATIVETRACE_TRANSCRIPT"])
    verdict = gv.Verdict()
    if args.kind == "explain":
        grade_explain(events, verdict)
    else:
        grade_control(events, verdict)
    sys.exit(1 if verdict.failed else 0)


if __name__ == "__main__":
    main()
