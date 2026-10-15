#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# narrativetrace-explain / explain-an-unfamiliar-flow — the case this skill exists for.
#
# Fixture: existing-service-checkout, NarrativeTrace already installed. The prompt names nothing of
# ours ("Show me what this application actually does when an order is placed"), nothing is broken
# and no change needs verifying, so this case measures the one thing no other skill covers:
# whether an ordinary execution-understanding request reaches the trace at all. PASS: the Skill tool
# invoked narrativetrace-explain, the run left a structural trace, that trace reached the agent
# before its answer, the answer cites a span id the trace actually carries, and the production code
# and pyproject.toml were left alone. Near misses: an answer written from the source with no run; a
# run whose trace nobody read; an id cited that is in no trace; the service "explained" by
# rewriting it.
# A red row that triggered but never traced is a wording problem in the page; a red row that never
# triggered is the trigger phrasing.
set -e
python3 "$(dirname "$0")/../../grade_the_explain.py" --kind explain
