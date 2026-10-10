#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# World-state verifier for the PUBLISHED init prompt reached through the Claude Code plugin
# MARKETPLACE. Exit 0 = gate passed. Run with cwd set to the scaffolded fixture copy.
#
# The runner's pre-step added the marketplace from a snapshot of HEAD and installed its one plugin
# at USER scope -- the only scope the documentation describes -- into a configuration directory the
# trial owns. So the pages are available to the agent and are in NO part of the project, which is
# this case's own subject: the installer still has a whole install to do, and the project must end
# up carrying nothing it did not write itself.
#
# This case's prompt.md IS the published prompt, byte for byte (test_init_prompt_drift.py enforces
# that), so what this grades is what a reader pasted after following the marketplace line in
# llms.txt.
set -e

sh "$(dirname "$0")/../../grade_the_registry.sh" claude-marketplace OrderService
