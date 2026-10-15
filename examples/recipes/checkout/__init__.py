# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The one checkout every recipe page under ``documentation/recipes/`` runs.

Plain code, no tracing in it: the recipes wrap it with ``trace_object`` and read what a real run
wrote (rule 8, docs as tests -- ``recipe_artifacts.py`` produces every file a page embeds, and
``poe snippet-check`` holds each page to them). Not published.
"""
