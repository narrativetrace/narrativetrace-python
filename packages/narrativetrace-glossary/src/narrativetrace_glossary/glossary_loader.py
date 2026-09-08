# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Runtime discovery of the committed glossary for translation.

``GlossaryLoader``. INTENT: absence is a normal state — a project that has not opted into
translated views yet — but a directory a caller *named* explicitly and that turns out empty is a
configuration mistake, not an absence, and fails fast rather than silently rendering untranslated.

Shares ``NARRATIVETRACE_GLOSSARY_DIR``/``glossary_dir`` with
:func:`~narrativetrace_glossary.vocabulary.read_project_vocabulary`: one configuration key names
where a repository's glossary lives, for both consumers, rather than two overlapping ones (a
deliberate divergence from Java/.NET, which resolve a translation-specific path separately from
their build-time vocabulary discovery — this runtime's
:class:`~narrativetrace.config.ConfigResolver` already unifies configuration resolution, so a
second key would only mean the same thing twice).
"""

from __future__ import annotations

from pathlib import Path

from narrativetrace.config import ConfigResolver
from narrativetrace_glossary.json_reader import read_glossary_json
from narrativetrace_glossary.models import Glossary
from narrativetrace_glossary.vocabulary import GLOSSARY_FILE


def load_glossary(
    resolver: ConfigResolver | None = None, *, default_dir: str | Path = "."
) -> Glossary | None:
    """Loads the committed glossary for translation, or ``None`` when none is configured.

    Args:
        resolver: supplies ``glossary_dir`` (env ``NARRATIVETRACE_GLOSSARY_DIR``); a fresh
            :class:`~narrativetrace.config.ConfigResolver` when omitted.
        default_dir: where to look when nothing was explicitly configured. Defaults to the
            current working directory, matching every other unconfigured-default in this
            distribution; overridable so a caller (or a test) can pin the directory without
            changing the process's real working directory.

    Returns:
        The parsed glossary, or ``None`` when no directory was explicitly configured and
        ``default_dir`` holds no ``glossary.json`` — the ordinary state for a project that has
        not opted into translated views.

    Raises:
        ValueError: the committed file exists but is malformed, or a directory named explicitly
            (via config file or environment) holds no ``glossary.json`` at all.
    """
    active_resolver = resolver if resolver is not None else ConfigResolver()
    configured = active_resolver.resolve("glossary_dir", None)
    glossary_dir = Path(configured) if configured is not None else Path(default_dir)
    path = glossary_dir / GLOSSARY_FILE
    if not path.is_file():
        if configured is not None:
            raise ValueError(f"configured glossary directory {glossary_dir} has no {GLOSSARY_FILE}")
        return None
    return read_glossary_json(path.read_text(encoding="utf-8"))
