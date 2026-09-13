# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``uv run python -c ...`` one-liners shared between ``narrativetrace-doctor`` and
``add-narrative-tracing`` — both skills call the same doctor CLI, so the literal command text
lives here once rather than twice. Closed-vocabulary by design: every command's first token is
``uv`` (this port's toolchain is ``uv``, and through it the project venv's own
``python``/``pytest``/``narrativetrace`` — never a global binary).

Python-specific adaptation from the TypeScript reference (worth stating explicitly): the
TypeScript fixture's committed test suite already produces real ``narrativetrace-output/`` and
approval-trace artifacts before its "read the rendered trace"/"approval flow" steps replay, so
those commands hard-fail when nothing is there. This port's canonical fixture
(``examples/sixty_seconds``) is a plain script walkthrough with no such committed output, so both
commands here degrade GRACEFULLY (exit 0, informational message) when nothing has been rendered
yet — the same "nothing to check yet" stance ``trap.parameter-names``/``trap.approval-traces``
already take in the doctor CLI itself, rather than a hard failure Tier A2 could never turn green
against this fixture.
"""

from __future__ import annotations

_CHECK_FINDINGS_WELL_FORMED = """\
import json, sys
report = json.load(sys.stdin)
findings = report.get("findings")
sys.exit(1 if not isinstance(findings, list) or len(findings) != 11 else 0)
"""

DOCTOR_REPORT_WELL_FORMED = (
    f"uv run narrativetrace doctor --json | uv run python -c '{_CHECK_FINDINGS_WELL_FORMED}'"
)
"""Runs ``narrativetrace doctor`` and asserts the report is well-formed (parses, carries all
eleven finding ids) — the mechanical floor a step can claim just from "doctor ran". It does NOT
assert any finding's pass/fail VALUE: those are already unit-tested per-check at the CLI layer,
and a project's report legitimately fails some checks while still being well-formed — that is
doctor working correctly, not a defect in whatever step is running this."""

_CHECK_TOOLCHAIN_HOLDS = """\
import json, sys
report = json.load(sys.stdin)
bad = [f for f in report["findings"] if f["id"].startswith("toolchain.") and f["status"] != "pass"]
if bad:
    print(json.dumps(bad))
sys.exit(1 if bad else 0)
"""

TOOLCHAIN_CHECKS_HOLD = (
    f"uv run narrativetrace doctor --json | uv run python -c '{_CHECK_TOOLCHAIN_HOLDS}'"
)
"""Every ``toolchain.*`` finding holds (status ``pass``) — the install step's own claim, not a
repeat of the install command itself."""

_CHECK_REDACTION_PROOF_PRESENT = """\
import json, sys
report = json.load(sys.stdin)
by_id = {f["id"]: f for f in report["findings"]}
finding = by_id.get("trap.redaction-proof")
sys.exit(1 if finding is None or finding["status"] not in ("pass", "fail") else 0)
"""

REDACTION_PROOF_FINDING_PRESENT = (
    f"uv run narrativetrace doctor --json | uv run python -c '{_CHECK_REDACTION_PROOF_PRESENT}'"
)
"""The ``trap.redaction-proof`` finding is present and well-formed — the redaction step's own
claim. Deliberately does NOT assert ``status == "pass"``: a project with no redaction test yet
legitimately reports ``fail`` here, and this step's job is proving the CHECK ITSELF ran, not
asserting the outcome a still-unwritten test would produce."""

_REDACTION_TEST_GUIDANCE_SCRIPT = """\
print(
    "Render a call with a deny-listed parameter name (e.g. password or token) in a test and "
    "assert the output contains [REDACTED], and that a neighboring non-sensitive value is still "
    "present."
)
"""

REDACTION_TEST_GUIDANCE = f"uv run python -c '{_REDACTION_TEST_GUIDANCE_SCRIPT}'"
"""Echoes the "write the test" guidance the redaction step asks for — a no-op, always-succeeds
command."""

_OPEN_NEWEST_RENDERED_TRACE_SCRIPT = """\
import pathlib
root = pathlib.Path("narrative-traces")
files = sorted(root.rglob("*.md"), key=lambda p: p.stat().st_mtime) if root.is_dir() else []
if not files:
    print("no rendered .md file found yet under narrative-traces -- run your tests or app once")
else:
    newest = files[-1]
    print(newest)
    print(newest.read_text(encoding="utf-8"))
"""

OPEN_NEWEST_RENDERED_TRACE = f"uv run python -c '{_OPEN_NEWEST_RENDERED_TRACE_SCRIPT}'"
"""Opens the newest rendered Markdown trace under the output directory — never a fixture path, so
the same command works whatever a real project scenario is named. Exits 0 either way (see the
module docstring's fixture-shape note): nothing rendered yet is reported, not failed."""

_APPROVAL_FLOW_DIFF_SCRIPT = """\
import pathlib
root = pathlib.Path("test-narratives")
received = sorted(root.rglob("*.received.nt")) if root.is_dir() else []
if not received:
    print("no approval traces configured yet under test-narratives -- nothing pending")
else:
    newest = received[-1]
    approved = newest.with_name(newest.name.replace(".received.nt", ".approved.nt"))
    print("received: " + str(newest))
    if approved.is_file():
        print("approved: " + str(approved))
        print(approved.read_text(encoding="utf-8"))
        print("--- vs received ---")
    else:
        print("no .approved.nt yet -- first approval, review then promote")
    print(newest.read_text(encoding="utf-8"))
"""

APPROVAL_FLOW_DIFF = f"uv run python -c '{_APPROVAL_FLOW_DIFF_SCRIPT}'"
"""If a ``.received.nt`` sits beside an ``.approved.nt``, diffs them; otherwise reports nothing
pending. Never a fixture path. Exits 0 either way (see the module docstring)."""
