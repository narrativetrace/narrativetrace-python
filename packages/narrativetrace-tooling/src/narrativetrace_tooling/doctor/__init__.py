# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace doctor`` — read-only, zero-network diagnosis of a project's NarrativeTrace
install and configuration.

Mirrors the TypeScript runtime's ``@narrativetrace/cli`` doctor (``packages/cli/src/doctor/``):
twelve checks with stable, dotted ids, a pure
:class:`~narrativetrace_tooling.doctor.types.DoctorCheck` signature over a
:class:`~narrativetrace_tooling.doctor.types.DoctorSnapshot`, and one impure module that builds that
snapshot from the real filesystem. Every check is a pure function: given the same snapshot it always
returns the same :class:`~narrativetrace_tooling.doctor.types.Finding` — which is what makes each
check unit-testable with no disk I/O and no subprocess. Every check reads only the standard library
(``importlib.metadata``, ``sys``, ``tomllib``, ``pathlib``), like the rest of this distribution.

**The split across two distributions, and why it falls where it does.** The checks, the report and
both renderings live here, in the zero-dependency library that the ``narrativetrace`` console script
and any later entry point both embed. The two impure parts stay in the ``narrativetrace``
distribution: :mod:`narrativetrace.doctor.environment`, which builds the snapshot, and
:mod:`narrativetrace.doctor.cli_bin`, the console script. The reader stays there because it resolves
a project's configuration through :class:`narrativetrace.config.ConfigResolver` — the same resolver
the runtime itself uses — and a reader that reimplemented that precedence would diagnose a project
differently from the runtime it is diagnosing. A library that imported it would also close a cycle,
since the console script depends on this library.

Not a public API for consumers to import: reached through the ``narrativetrace`` console script, the
same way ``narrativetrace-approve`` (:mod:`narrativetrace.cli`) is a console-script-only module.
"""

from __future__ import annotations
