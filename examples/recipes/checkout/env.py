# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The environment variables the recipe scenarios and ``recipe_artifacts.py`` agree on.

Build plumbing only -- none of these is a NarrativeTrace setting, and no recipe page asks a reader
to set one.
"""

LOG_FILE_ENV = "NARRATIVETRACE_RECIPE_LOG"
"""The file the scenarios' ``logging`` handler writes (stdout when unset)."""

REFACTORED_ENV = "NARRATIVETRACE_RECIPE_REFACTORED"
"""Any non-empty value wires the refactored checkout (the one that dropped the release)."""

VERDICTS_ENV = "NARRATIVETRACE_RECIPE_VERDICTS"
"""The file ``verdict_plugin`` appends what the runner reported to."""
