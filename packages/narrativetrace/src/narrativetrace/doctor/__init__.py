# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace doctor``'s one impure half, and the console script every verb goes through.

Every check, the report, both renderings and the whole agent-skills installer live in
:mod:`narrativetrace_tooling` — the zero-dependency library this distribution's console script
launches, and which a second entry point can embed without dragging the runtime in with it. What
stays here is what cannot move:

* :mod:`narrativetrace.doctor.environment` — builds the
  :class:`~narrativetrace_tooling.doctor.types.DoctorSnapshot` by walking the real project and the
  installed-distribution metadata. It resolves configuration through
  :class:`narrativetrace.config.ConfigResolver`, the same resolver the runtime itself uses, so the
  doctor reads a project exactly as the runtime does rather than guessing at the precedence again.
* :mod:`narrativetrace.doctor.cli_bin` — the ``narrativetrace`` console script: verb dispatch for
  ``doctor``, ``init`` and ``uninstall``, process exit codes, stdout and stderr. It sits beside the
  doctor's reader rather than higher up because ``doctor`` was its first verb and this module path
  is the one ``[project.scripts]`` names; the launcher itself is about all three.

Not part of the package's public API (:mod:`narrativetrace`'s ``__all__``) — reached only through
the ``narrativetrace`` console script, the same way ``narrativetrace-approve``
(:mod:`narrativetrace.cli`) is a console-script-only module.
"""

from __future__ import annotations
