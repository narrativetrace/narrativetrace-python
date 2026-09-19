#!/usr/bin/env bash
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# Post-publish marker settle: after a tag publish, mechanically rewrites every in-tree doc marker
# `*(since <version>, unreleased)*` for that exact version to `*(since <version>)*`, restamps any
# translated mirror it touched, and refreshes the docs-vs-published banner. See
# scripts/settle_markers.py for the full design note and this repository's own release procedure
# for where this step sits in it. Thin wrapper only -- all logic lives in the Python module so it
# is unit-testable without a subprocess.
#
# Usage: scripts/settle-markers.sh <version>
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 -m scripts.settle_markers "$@"
