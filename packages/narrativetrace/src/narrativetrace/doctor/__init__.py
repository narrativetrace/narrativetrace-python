# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace doctor`` — read-only, zero-network diagnosis of a project's NarrativeTrace
install and configuration *(since 0.1.2, unreleased)*.

Mirrors the TypeScript runtime's ``@narrativetrace/cli`` doctor (``packages/cli/src/doctor/``):
eleven checks with stable, dotted ids, a pure :class:`~narrativetrace.doctor.types.DoctorCheck`
signature over a :class:`~narrativetrace.doctor.types.DoctorSnapshot`, and one impure module
(:mod:`narrativetrace.doctor.environment`) that builds the snapshot from the real filesystem.
Every check is a pure function: given the same snapshot, it always returns the same
:class:`~narrativetrace.doctor.types.Finding` — which is what makes each check unit-testable with
no disk I/O and no subprocess. Lives in the core, dependency-free distribution: every check reads
only the standard library (``importlib.metadata``, ``sys``, ``tomllib``, ``pathlib``).

Not part of the package's public API (:mod:`narrativetrace`'s ``__all__``) — reached only through
the ``narrativetrace`` console script (:mod:`narrativetrace.doctor.cli_bin`), the same way
``narrativetrace-approve`` (:mod:`narrativetrace.cli`) is a console-script-only module.
"""

from __future__ import annotations
