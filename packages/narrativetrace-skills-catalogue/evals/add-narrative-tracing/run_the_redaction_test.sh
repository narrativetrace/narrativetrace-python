#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# Grades the published init prompt's step 5 -- "Add one test that traces a call with a
# deny-listed parameter and asserts the trace shows [REDACTED] for it" -- as world state: a test
# file makes the assertion, and the project's own test suite actually passes it. Shared by both
# init-prompt cases; run with cwd set to the scaffolded fixture copy, from a case's
# graders/verify.sh.
set -e

if ! grep -rlE '\[REDACTED\]' --include="test_*.py" --include="*_test.py" . 2>/dev/null \
  | grep -v '/\.venv/' | grep -q .; then
  echo "expected a test_*.py/*_test.py file to assert [REDACTED] for a deny-listed parameter" >&2
  exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
log="$work/pytest-output.txt"

# Bounded, always: a cold run resolves and downloads the packages, and a suite that hangs has to
# fail this case rather than the whole harness (mirrors run_the_program.sh's own bound).
if ! timeout 900 uv run pytest -q >"$log" 2>&1; then
  echo "the redaction test must actually pass -- the prompt says to add and prove it, not just assert it exists" >&2
  cat "$log" >&2
  exit 1
fi

echo "run_the_redaction_test.sh: a test asserts [REDACTED] for a deny-listed parameter, and the suite passes"
