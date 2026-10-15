#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# `bounded <seconds> <command...>` -- the one way the graders put a time limit on a build or a run.
#
# GNU `timeout` where the platform has it (Linux, the trial container); macOS ships no coreutils
# `timeout`, so a Mac run of any grader died with `timeout: command not found` at the first bounded
# step, which turned every init-prompt trial into a harness verdict (Java, 2026-10-10). The fallback
# is perl's alarm: the timer survives exec, and SIGALRM's default action ends the command. Both
# answers are non-zero on expiry (124 from timeout, 142 from the alarm), which is all a grader
# tests. Source it: `. "$(dirname "$0")/bounded.sh"`.
bounded() {
  if command -v timeout >/dev/null 2>&1; then
    timeout "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$@"
  else
    perl -e 'alarm shift @ARGV; exec @ARGV or die "exec: $!\n"' "$@"
  fi
}
