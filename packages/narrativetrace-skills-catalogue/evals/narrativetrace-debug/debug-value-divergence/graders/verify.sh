#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# narrativetrace-debug / debug-value-divergence (Phase 7, D4 and D6) — a symptom ticket whose defect
# is visible only in a value at a boundary.
#
# Fixture: existing-service-checkout-currency. Checkout issues the invoice in euro, reads the card's
# currency, converts with RateTableConverter and authorizes the converted amount. The converter
# rounds to whole francs before moving to cents, so 45.99 EUR at 0.93 is charged 4300, not 4277.
# Every test passes (the converter's unit tests only use amounts that land on whole units), and the
# structural trace looks right: the defect is
# #1.3 RateTableConverter.convert(euro_cents: 4599, currency: "CHF") → 4300 with its child
# DailyRates.rate_for returning the right 0.93. Turn 2 is the scripted "yes, pin it".
#
# PASS (every gating line of grade_the_debug.py): the reproduction's values were read, and the
# converter's span id — one the agent was SHOWN — named in its own words, before any production
# code changed; nothing promoted before the yes and the turn before it ended on the question; the
# suite passes; the converter's code changed and the grader's probe gets 4277 from it; with the
# fixture's production code put back, the agent's tests fail (a regression test exists) and every
# scenario's call shape is the same as in the final run (nothing else moved — read from the .md,
# because a red run writes no .nt); a .approved.nt pins a flow through the converter; no
# .received.nt is left; the agent's prose after the fix cites the converter's span id (the gate
# puts the report before the pin question; quoted trace lines do not count).
# Near misses it fails, each for its own reason: a fix that silences the symptom elsewhere (the
# converter untouched — its value is still wrong); a fix that bypasses the converter (the shape
# moved); fixed with no regression test; fixed before the span was named; never pinned; pinned
# before the yes; a report without the id.
set -e
python3 "$(dirname "$0")/../../grade_the_debug.py"
