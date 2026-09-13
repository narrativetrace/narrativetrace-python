# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Public doc anchors every finding points at — a stable GitHub blob link into this repository's
own ``documentation/`` on ``main``, the same choice the TypeScript runtime's ``doc-urls.ts`` makes
and for the same reason: this repository is public on GitHub, so a blob link is an honest "public
docs URL" today even before narrativetrace.ai carries the Python guides. The anchors are GitHub's
own heading slugs and do not change if the base ever moves to the docs site.
"""

from __future__ import annotations

_BASE = "https://github.com/narrativetrace/narrativetrace-python/blob/main/documentation/"

DOC = {
    "installation_prerequisites": f"{_BASE}guides/installation.md#installation",
    "pytest_configuration": f"{_BASE}guides/pytest.md#what-you-get",
    "where_settings_come_from": f"{_BASE}guides/configuration.md#where-settings-come-from",
    "output_settings": f"{_BASE}guides/configuration.md#output-settings-pytest-plugin",
    "config_keys": f"{_BASE}guides/configuration.md#where-settings-come-from",
    "no_trace_files_written": f"{_BASE}troubleshooting.md#no-trace-output-files",
    "parameter_names": (
        f"{_BASE}troubleshooting.md#a-args-methods-parameters-show-as-one-args-value"
    ),
    "redaction_surface_by_surface": f"{_BASE}privacy-and-redaction.md#redaction-surface-by-surface",
    "approval_traces_end_to_end": (
        f"{_BASE}guides/configuration.md#structural-artifact-and-approval-mode-since-012-unreleased"
    ),
    "sixty_seconds_new_project": f"{_BASE}sixty-seconds.md#1-new-project-install-the-package",
}
