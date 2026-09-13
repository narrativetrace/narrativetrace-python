# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``config.unknown-keys`` — every key a ``narrativetrace.toml`` (or ``[tool.narrativetrace]``
table) can carry is read through :class:`~narrativetrace.config.ConfigResolver`'s fixed set of
keys (``output``, ``output_dir``, ``format``, ``canonical``, ``approval``, ``approved_dir``,
``glossary``, ``glossary_dir``, ``level``). A misspelled key (``ouput_dir``, ``aproved_dir``) is
never rejected by :meth:`~narrativetrace.config.ConfigResolver.resolve` — it simply falls through
to the caller's default, exactly as if the key were absent, so a typo silently does nothing rather
than raising. This is the one check that catches it."""

from __future__ import annotations

from narrativetrace.doctor.doc_urls import DOC
from narrativetrace.doctor.finding import failed, passed
from narrativetrace.doctor.types import DoctorSnapshot, Finding

ID = "config.unknown-keys"

KNOWN_KEYS = frozenset(
    {
        "output",
        "output_dir",
        "format",
        "canonical",
        "approval",
        "approved_dir",
        "glossary",
        "glossary_dir",
        "level",
    }
)


def check_unknown_config_keys(snapshot: DoctorSnapshot) -> Finding:
    if not snapshot.narrativetrace_config:
        return passed(
            ID, "no narrativetrace configuration file found — nothing to check", DOC["config_keys"]
        )
    unknown = sorted(set(snapshot.narrativetrace_config) - KNOWN_KEYS)
    if not unknown:
        message = f"every configured key ({len(snapshot.narrativetrace_config)}) is recognized"
        return passed(ID, message, DOC["config_keys"])
    return failed(
        ID,
        f"unrecognized configuration key(s): {', '.join(unknown)}",
        "A key ConfigResolver does not recognize is silently ignored, never rejected — check for a "
        f"typo against the known keys ({', '.join(sorted(KNOWN_KEYS))}).",
        DOC["config_keys"],
    )
