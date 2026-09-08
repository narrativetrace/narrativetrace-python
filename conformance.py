# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Schema validation shared by every package's conformance tests.

The canonical output contract lives in ``schema/`` as JSON Schema documents copied
byte-identically from the shared master copy. Validating produced artifacts against them is what
turns silent schema drift into a failing build.

This module sits at the repository root rather than inside one package's ``tests`` directory
because two suites need it — the core exporters and the pytest plugin's writer-validated
artifacts — and a partial run (``pytest packages/narrativetrace-pytest``) puts only its own test
directory on ``sys.path``. The root is always importable: pytest's prepend import mode inserts the
directory holding the top-level ``conftest.py``.

``jsonschema`` is a **dev** dependency. Nothing here is imported by any distribution — the core
package stays dependency-free.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_DIR = Path(__file__).parent / "schema"
"""Directory holding the canonical schemas, resolved from this file rather than the cwd."""

ENTRY_SCHEMA = "entry.schema.json"
CHAPTER_SCHEMA = "chapter.schema.json"
CHAPTER_TREE_SCHEMA = "chapter-tree.schema.json"


@cache
def load_schema(name: str) -> dict[str, Any]:
    """Reads and caches one canonical schema by file name.

    Raises:
        FileNotFoundError: if the schema is missing — a silently skipped conformance check is
            worse than no check at all, so this never degrades to a no-op.
    """
    path = SCHEMA_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"canonical schema not found: {path}")
    parsed: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return parsed


def validate_against(document: object, schema_name: str) -> None:
    """Validates an already-parsed document against a canonical schema.

    Raises:
        jsonschema.ValidationError: on the first violation, naming the offending path.
    """
    jsonschema.validate(document, load_schema(schema_name))


def validate_json_text(text: str, schema_name: str) -> Any:
    """Parses artifact *bytes* and validates them, returning the parsed document.

    Prefer this over validating an in-memory dict: prerequisite 8 of the Java conformance plan is
    that the check runs against what the real writer put on disk, so a serialisation bug (a value
    that stringifies differently, a key the writer drops) cannot pass.
    """
    document = json.loads(text)
    validate_against(document, schema_name)
    return document
