#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# World-state verifier for the PUBLISHED init prompt (never output text equality). Exit 0 = gate
# passed. Run with cwd set to the scaffolded fixture copy.
#
# Grades exactly what the prompt promises, and nothing else: a project that declares NarrativeTrace,
# a program that runs and prints a trace, its own rules kept, and a clean doctor report. All of that
# is grade_the_prompt.sh, shared with every other case whose prompt.md is the same published text.
#
# The service name is the one llms.txt's own install block builds.
set -e

sh "$(dirname "$0")/../../grade_the_prompt.sh" OrderService
