#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# narrativetrace-verify / verify-unintended-interaction (Phase 7, D6) — the owner's demonstration.
#
# Fixture: existing-service-checkout. Side effects of a successful payment are registered on
# shopkit's checkout hooks in billing/compose.py (the ledger entry is one). shopkit — installed from
# the fixture's hidden .vendor/ path dependency, so its code is outside the project's readable
# source (cross-port item 9) — fires `payment_succeeded` right after PaymentGateway.authorize and
# BEFORE PaymentGateway.confirm, though its docstring says "once the payment has gone through". The
# natural solution — one more payment_succeeded hook — passes every test while the structural trace
# shows NotificationService.send before PaymentGateway.confirm. Turn 2 is the scripted "yes, pin it".
#
# PASS (every gating line of grade_the_verify.py --kind interaction): the intent is in the agent's
# own text before the first traced run (the run whose trace was first read) and before any .nt is
# read; no rendered narrative before the first .nt; nothing promoted before the yes, and the turn
# before the yes ended on the question; the suite passes and, in the grader's own final run, the
# receipt follows the confirmation; a .approved.nt pins that fixed flow and no .received.nt is
# left; the agent's prose after its last structural read cites a span id that is in the pinned
# baseline. Whether every call line of what was promoted was in a reply before the yes is
# REPORTED, not gated (as the feedback grader reports "the whole draft was shown").
# Near misses it fails, each for its own reason: done on green tests; read the trace but did not
# act; values first; never pinned; pinned before the yes; a report without an id; intent after run.
set -e
python3 "$(dirname "$0")/../../grade_the_verify.py" --kind interaction
