# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The structlog row's wiring, as the framework table shows it: ``narrative_context_processor`` in
the processor chain ``structlog.configure`` installs. Compiled and exercised by
``test_structlog_wiring.py``; the doctor's ``config.structlog-processor`` fix and ``llms-full.md``
carry the ``wiring`` region verbatim (``narrativetrace_tooling/frameworks/wiring-snippets.md``)."""

from __future__ import annotations

# snippet:begin wiring
import structlog
from narrativetrace_structlog import narrative_context_processor

structlog.configure(
    processors=[narrative_context_processor, structlog.processors.JSONRenderer()],
)
# snippet:end wiring
