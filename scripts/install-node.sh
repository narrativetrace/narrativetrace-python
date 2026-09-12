#!/usr/bin/env bash
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# Installs Node.js (>=18, jscpd's own floor -- `npm view jscpd@<pinned> engines`) into the CI
# image, where `ghcr.io/astral-sh/uv:python3.12-bookworm` ships none (verified by hand,
# 2026-09-12: a fresh container has no `node`/`npx` on PATH). `scripts/duplication_report.py`'s
# own missing-Node gate (`decide_missing_node`) covers a machine that skips this script entirely
# (a local run, no Node): this is only for the one environment that must not skip -- CI, where
# the duplication ratchet is a per-commit gate, not an optional local nicety.
#
# apt's own `nodejs`/`npm` packages are enough: Debian bookworm (this image's base) carries
# 18.20.x, which already clears jscpd's floor -- no NodeSource script, no version pin to keep in
# step with a second upstream.
#
# Usage: scripts/install-node.sh   # CI only; a dev machine already has Node
set -euo pipefail

if command -v node >/dev/null 2>&1; then
    echo ">> Node already on PATH: $(node --version)"
    exit 0
fi

if ! command -v apt-get >/dev/null 2>&1; then
    echo "ERROR: no apt-get and no Node on PATH -- install Node.js >=18 manually" >&2
    exit 1
fi

echo ">> Installing nodejs/npm via apt-get"
apt-get update -qq
apt-get install -y -qq --no-install-recommends nodejs npm

echo ">> Installed: node $(node --version), npm $(npm --version)"
