# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The framework table (Phase 6 D1) — which frameworks NarrativeTrace integrates with, how a
project proves it uses one, what it adds, how that is wired, and which doctor check watches it.

Ships inside the doctor's own library so a project is measured against the rows of the version it
installed (D2 as amended): :mod:`~narrativetrace_tooling.frameworks.table` holds the rows,
:mod:`~narrativetrace_tooling.frameworks.manifests` reads what a project declares,
:mod:`~narrativetrace_tooling.frameworks.evidence` what its source applies, and
:mod:`~narrativetrace_tooling.frameworks.wiring_snippets` the lines a fix prints.
"""
