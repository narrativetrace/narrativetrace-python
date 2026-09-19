# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The corpus's own PROSE -- the fields a reader reads, not the bytes a case plants -- must be
publishable as it stands. Mirrors Java's ``CorpusProseIsPublishableTest``.

INTENT: The hostile corpus is the cross-port master copy: every runtime mirrors these files
byte-identically, and they ship in the public snapshot of each. A row written during private work
therefore carries that work's vocabulary straight into four public repositories -- a commit SHA
nobody outside can resolve, or the name of an internal process -- and the publish reference gate
rejects the mirrored file downstream, in a repository whose author cannot fix the text. Catching it
here, in the master copy (and its verbatim mirror), is the only place the fix is one edit rather
than five.

Scans ``id``, ``kind``, ``description`` and ``member`` ONLY. The payload fields -- a canary, a
value, a field name -- are the hostile data itself: a national-id shape or a token fixture may
legitimately be a long run of hex digits, and a deny-list vocabulary row may legitimately name any
field an application ever declared. The prose fields are the ones written for a human, and they are
the ones that must read as a statement of the rule the row pins.

The hex rule is deliberately bounded at seven characters, the shortest abbreviated SHA git
resolves. Shorter runs -- ``cafe``, ``dead``, a four-digit year -- are ordinary English and
ordinary data.
"""

from __future__ import annotations

import re

from hostile_corpus import GraphCase, RedactionCase, graphs, redactions

# An abbreviated or full commit SHA: what a public reader cannot resolve.
_COMMIT_SHA = re.compile(r"\b[0-9a-f]{7,40}\b")

# Vocabulary of the private process, never of the rule a row pins.
_PRIVATE_PROCESS = re.compile(r"pair\s*#|\bagent\b|\bcoordinator\b", re.IGNORECASE)


def _offending_matches(field: str | None) -> list[str]:
    if field is None:
        return []
    return _COMMIT_SHA.findall(field) + _PRIVATE_PROCESS.findall(field)


def _assert_prose_is_publishable(case_id: str, fields: list[str | None]) -> None:
    offending: list[str] = []
    for field in fields:
        offending.extend(_offending_matches(field))
    assert not offending, (
        f"{case_id}: corpus prose ships publicly and must name the rule, not the private work "
        f"({offending!r})"
    )


def _graph_fields(case: GraphCase) -> list[str | None]:
    return [case.id, case.kind, case.description, case.member]


def _redaction_fields(case: RedactionCase) -> list[str | None]:
    return [case.id, case.kind, case.description]


class TestCorpusProseIsPublishable:
    def test_no_graph_rows_prose_carries_a_commit_sha_or_the_vocabulary_of_the_private_process(
        self,
    ) -> None:
        for graph_case in graphs():
            _assert_prose_is_publishable(graph_case.id, _graph_fields(graph_case))

    def test_no_redaction_rows_prose_carries_a_commit_sha_or_the_vocabulary_of_the_private_process(
        self,
    ) -> None:
        for redaction_case in redactions():
            _assert_prose_is_publishable(redaction_case.id, _redaction_fields(redaction_case))
