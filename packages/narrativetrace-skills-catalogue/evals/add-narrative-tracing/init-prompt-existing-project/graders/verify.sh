#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# World-state verifier for the PUBLISHED init prompt against a project that already exists (never
# output text equality). Exit 0 = gate passed. Run with cwd set to the scaffolded fixture copy.
#
# What the prompt promises is grade_the_prompt.sh, shared with every other case whose prompt.md is
# the same published text. What is this case's own is the one assertion below: step 2's other half
# says to trace a REAL service boundary in the project that is already here, never a demo beside
# it, so the fixture's own implementation has to still be there and the trace has to name its class.
set -e

test -f src/billing/invoice_service.py || {
  echo "the fixture's existing implementation must still be there" >&2
  exit 1
}

sh "$(dirname "$0")/../../grade_the_prompt.sh" InvoiceService
