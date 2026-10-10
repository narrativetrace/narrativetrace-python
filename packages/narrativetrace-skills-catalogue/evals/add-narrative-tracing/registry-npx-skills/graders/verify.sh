#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# World-state verifier for the PUBLISHED init prompt reached through `npx skills add`. Exit 0 = gate
# passed. Run with cwd set to the scaffolded fixture copy.
#
# The runner's pre-step ran the registry tool against a snapshot of HEAD, so the project starts with
# the open-standard pages as real files, .claude/skills/<name> as a SYMBOLIC LINK to each of them,
# and the tool's own lock file at the root. That tree is this case's subject: before adoption it was
# refused as somebody else's work, and the --force a reader would then have reached for would have
# written the vendor flavour through the link and destroyed the page it had just adopted.
#
# This case's prompt.md IS the published prompt, byte for byte (test_init_prompt_drift.py enforces
# that), so what this grades is what a reader pasted after following the `npx skills add` line in
# llms.txt.
set -e

sh "$(dirname "$0")/../../grade_the_registry.sh" npx-skills OrderService
