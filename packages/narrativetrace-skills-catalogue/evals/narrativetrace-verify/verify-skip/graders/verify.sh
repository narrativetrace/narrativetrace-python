#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# narrativetrace-verify / verify-skip (Phase 7, D2 and D6) — the cost rule.
#
# Fixture: existing-service-checkout. The task caps billing.late_fees.fee_for, a pure function with
# its own unit test and no collaborator: tracing it is waste. PASS: the suite passes and the cap
# holds (the grader adds one probe test to the scratch copy); no structural trace reached the agent;
# no approval baseline was written and approval mode was not switched on; and the transcript says
# the skill was skipped and why (a pure function, no collaborator, one class). Loading the skill to
# make that decision is fine — its first step IS the decision; tracing after it is the failure.
# Near misses: traced the trivial change anyway; skipped without saying so.
set -e
python3 "$(dirname "$0")/../../grade_the_verify.py" --kind skip
