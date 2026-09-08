# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Root pytest configuration.

Enables the ``pytester`` fixture used by narrativetrace-pytest's plugin integration tests
(``pytest_plugins`` must live in a top-level conftest per pytest's rules).
"""

pytest_plugins = ["pytester"]
