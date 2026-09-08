# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Marker package for the ``narrativetrace-security-tests`` distribution.

This distribution has no importable production API -- like its Java counterpart (a Gradle module
with no ``src/main``), it exists to be built and tested like every other workspace member, never
to be installed by a consumer. All of its real code (the hostile-corpus loader, the object-graph
builder, the shared oracles, and the property tests themselves) lives under ``tests/`` and is
imported by bare module name the way ``narrativetrace-glossary``'s ``glossary_strategies`` is,
since pytest puts a ``tests/`` directory with no ``__init__.py`` on ``sys.path`` for its own
collected modules.

See ``README.md`` in this directory for why the package exists at all and how it is kept out of
the publish pipeline.
"""
