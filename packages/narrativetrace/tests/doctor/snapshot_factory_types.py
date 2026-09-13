# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Type aliases for the ``make_snapshot``/``package_info`` fixtures (``conftest.py``, excluded
from mypy like every conftest in this repo): every check test file imports these to annotate the
fixture parameters on its own test functions, the same way ``test_alias_index.py`` annotates its
``index`` fixture with the production ``Mapping[TermKey, GlossaryTerm]`` type directly rather than
leaving it unannotated under ``mypy --strict``."""

from __future__ import annotations

from collections.abc import Callable

from narrativetrace.doctor.types import DoctorSnapshot, PackageInfo

MakeSnapshot = Callable[..., DoctorSnapshot]
MakePackageInfo = Callable[..., PackageInfo]
