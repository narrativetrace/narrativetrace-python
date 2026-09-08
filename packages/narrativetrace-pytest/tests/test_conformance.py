# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Writer-validated conformance: the bytes on disk must satisfy the canonical schemas.

Prerequisite 8 of the Java conformance plan. Validating an in-memory document proves the mapper is
right; validating what the *real writer* put on disk is what catches a serialisation bug — and it
is what caught `scenario.result` carrying the display spelling `PASSED` into an artifact whose
schema allows only `success`/`error`.

Each test drives a full pytest run in a subprocess (the plugin's real entry point, real config
resolution, real writer), then reads the artifact back off disk and validates it.
"""

from __future__ import annotations

import json

import pytest
from conformance import CHAPTER_TREE_SCHEMA, ENTRY_SCHEMA, validate_against, validate_json_text

_SERVICE = """
from narrativetrace.trace_object import trace_object


class PaymentGateway:
    def charge(self, customer_id, amount):
        return {"transaction": "tx-1", "amount": amount}

    def refuse(self, customer_id):
        raise ValueError("card expired")
"""


def _run_with_output(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, body: str
) -> pytest.Pytester:
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "1")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(pytester.path / "nt-out"))
    pytester.makepyfile(_SERVICE + body)
    return pytester


def _artifact(pytester: pytest.Pytester, test_module: str, slug: str) -> str:
    path = pytester.path / "nt-out" / "traces" / test_module / f"{slug}.json"
    assert path.is_file(), f"the writer produced no artifact at {path}"
    return path.read_text(encoding="utf-8")


def test_a_passing_scenarios_artifact_satisfies_the_chapter_tree_schema(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_with_output(
        pytester,
        monkeypatch,
        """

def test_charges_a_customer(narrative_trace):
    trace_object(PaymentGateway(), narrative_trace).charge("cust-1", 42)
""",
    )

    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)

    document = validate_json_text(
        _artifact(
            pytester,
            "test_a_passing_scenarios_artifact_satisfies_the_chapter_tree_schema",
            "test_charges_a_customer",
        ),
        CHAPTER_TREE_SCHEMA,
    )
    assert document["scenario"]["result"] == "success"


def test_a_failing_scenarios_artifact_satisfies_the_chapter_tree_schema(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The spelling that used to break the schema: a failed test wrote `FAILED` into `result`."""
    _run_with_output(
        pytester,
        monkeypatch,
        """
import pytest


def test_refuses_an_expired_card(narrative_trace):
    with pytest.raises(ValueError):
        trace_object(PaymentGateway(), narrative_trace).refuse("cust-1")
    raise AssertionError("forced failure")
""",
    )

    result = pytester.runpytest_subprocess()
    result.assert_outcomes(failed=1)

    document = validate_json_text(
        _artifact(
            pytester,
            "test_a_failing_scenarios_artifact_satisfies_the_chapter_tree_schema",
            "test_refuses_an_expired_card",
        ),
        CHAPTER_TREE_SCHEMA,
    )
    assert document["scenario"]["result"] == "error"


def test_a_suppressed_value_artifact_still_satisfies_the_schema(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Below DETAIL no parameter values are captured; `value` must still be the string the
    schema requires, never null."""
    monkeypatch.setenv("NARRATIVETRACE_LEVEL", "NARRATIVE")
    _run_with_output(
        pytester,
        monkeypatch,
        """

def test_charges_a_customer(narrative_trace):
    trace_object(PaymentGateway(), narrative_trace).charge("cust-1", 42)
""",
    )

    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)

    validate_json_text(
        _artifact(
            pytester,
            "test_a_suppressed_value_artifact_still_satisfies_the_schema",
            "test_charges_a_customer",
        ),
        CHAPTER_TREE_SCHEMA,
    )


_CANONICAL_BODY = """

def test_charges_a_customer(narrative_trace):
    trace_object(PaymentGateway(), narrative_trace).charge("cust-1", 42)
"""


def test_the_canonical_artifact_is_written_only_when_the_switch_is_on(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_with_output(pytester, monkeypatch, _CANONICAL_BODY)

    pytester.runpytest_subprocess().assert_outcomes(passed=1)

    traces = (
        pytester.path
        / "nt-out"
        / "traces"
        / "test_the_canonical_artifact_is_written_only_when_the_switch_is_on"
    )
    assert not (traces / "test_charges_a_customer.canonical.json").exists()


def test_every_entry_of_the_canonical_artifact_satisfies_the_entry_schema(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NARRATIVETRACE_CANONICAL", "1")
    _run_with_output(pytester, monkeypatch, _CANONICAL_BODY)

    pytester.runpytest_subprocess().assert_outcomes(passed=1)

    text = _artifact(
        pytester,
        "test_every_entry_of_the_canonical_artifact_satisfies_the_entry_schema",
        "test_charges_a_customer.canonical",
    )
    entries = json.loads(text)
    assert [entry["nt.eventType"] for entry in entries] == ["method_enter", "method_exit"]
    for entry in entries:
        validate_against(entry, ENTRY_SCHEMA)


def test_the_canonical_artifact_carries_the_identity_captured_by_the_real_proxy(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 1.2 identity fields have to survive real capture, not just a hand-built signature."""
    monkeypatch.setenv("NARRATIVETRACE_CANONICAL", "1")
    _run_with_output(
        pytester,
        monkeypatch,
        """
from narrativetrace.decorators import narrated


class Ledger:
    @narrated("posts {amount} for {customer_id}")
    def post(self, customer_id: str, amount: int) -> bool:
        return True


def test_posts_an_amount(narrative_trace):
    trace_object(Ledger(), narrative_trace).post("cust-1", 42)
""",
    )

    pytester.runpytest_subprocess().assert_outcomes(passed=1)

    module = "test_the_canonical_artifact_carries_the_identity_captured_by_the_real_proxy"
    enter = json.loads(_artifact(pytester, module, "test_posts_an_amount.canonical"))[0]
    validate_against(enter, ENTRY_SCHEMA)
    assert enter["nt.package"] == module
    assert enter["nt.returnType"] == "builtins.bool"
    assert enter["nt.narrationTemplate"] == "posts {amount} for {customer_id}"
    assert {p["name"]: p.get("type") for p in enter["nt.parameters"]} == {
        "customer_id": "builtins.str",
        "amount": "builtins.int",
    }
    assert enter["thread.name"]
    assert enter["nt.threadVirtual"] is False


def test_a_redacted_parameter_artifact_still_satisfies_the_schema(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_with_output(
        pytester,
        monkeypatch,
        """
from narrativetrace.decorators import not_traced
from narrativetrace.trace_object import trace_object


class Vault:
    @not_traced("secret")
    def store(self, name, secret):
        return "stored"


def test_stores_a_secret(narrative_trace):
    trace_object(Vault(), narrative_trace).store("key", "hunter2")
""",
    )

    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)

    document = validate_json_text(
        _artifact(
            pytester,
            "test_a_redacted_parameter_artifact_still_satisfies_the_schema",
            "test_stores_a_secret",
        ),
        CHAPTER_TREE_SCHEMA,
    )
    parameters = document["events"][0]["parameters"]
    assert {"name": "secret", "value": "[REDACTED]", "redacted": True} in parameters
