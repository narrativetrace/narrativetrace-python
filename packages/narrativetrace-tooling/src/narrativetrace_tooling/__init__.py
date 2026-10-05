# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The free-tier tooling library: the read-only doctor and the agent-skills installer.

Standard library only, zero network, and — by contract — no import of ``narrativetrace`` itself.
This library reads a project's configuration, source tree and rendered output as text, and reads a
skills carrier through :mod:`importlib.metadata`, which resolves an installed distribution's own
files without importing it. That is what lets the ``narrativetrace`` console script sit *above* this
library and depend on it with no cycle, mirroring the Java port, where the CLI and the build plugin
both embed the same tooling library and neither depends on the other.

Two subpackages, each with its own entry in the architecture test that pins the rule above:

* :mod:`narrativetrace_tooling.doctor` — every check, the report, and both renderings. Each check is
  a pure function of one snapshot, which is why each has a passing and a failing unit test with no
  disk at all. The one impure part, the snapshot reader, stays in the ``narrativetrace``
  distribution: it resolves configuration through that distribution's own resolver, and a reader
  that guessed instead would diagnose a project differently from the runtime it is diagnosing.
* :mod:`narrativetrace_tooling.init` — the installer: carrier reader, project snapshot, pure
  planners, the only writer, and the renderers.

Not a public API for consumers to import: reached through the ``narrativetrace`` console script.
"""

from __future__ import annotations
