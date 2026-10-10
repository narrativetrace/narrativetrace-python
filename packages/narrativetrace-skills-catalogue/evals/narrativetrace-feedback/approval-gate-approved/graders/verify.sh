#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# Transcript + world-state verifier for the approval gate, APPROVED variant. Exit 0 = gate passed.
# The case's documentation is the header of ../../grade_the_approval_gate.py; prompt.md is the
# user's words and nothing else. Run with cwd set to the scaffolded fixture copy.
set -e

python3 "$(dirname "$0")/../../grade_the_approval_gate.py" --answer approve --case "$(dirname "$0")/.."
