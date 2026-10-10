# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""This repository's own test session disables the narrativetrace plugin (``-p no:narrativetrace``
in the root ``addopts``, so its import cannot skew coverage), which leaves ``narrative_trace``
undefined there. A test that needs the fixture is skipped in that session only; run from this
directory with ``-p narrativetrace`` — as the skills' replay does — it runs and writes its
artifacts, which is what it is for."""

import pytest


def pytest_collection_modifyitems(config, items):
    if config.pluginmanager.has_plugin("narrativetrace"):
        return
    skip = pytest.mark.skip(reason="the narrativetrace plugin is disabled in this session")
    for item in items:
        if "narrative_trace" in getattr(item, "fixturenames", ()):
            item.add_marker(skip)
