# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Logging for the two recipes about which trace, service and thread a line belongs to.

Unlike ``conftest.py``'s one-line-per-call format these put the raw trace id (and, for threads, the
thread) in every line, because that is what those pages follow. ``correlation_handler`` is this
build's plumbing (it points the handler at the file a page embeds); the filter and the format
strings are what a project writes.
"""

import logging
import os
from pathlib import Path

from examples.recipes.checkout.env import CORRELATION_LOG_FILE_ENV

# snippet:begin services-format
SERVICES_FORMAT = "%(levelname)-5s [%(name)s] [%(traceId)s] - %(message)s"
# snippet:end services-format
# snippet:begin threads-format
THREADS_FORMAT = "%(levelname)-5s [%(threadName)s] [%(name)s] [%(traceId)s] - %(message)s"
# snippet:end threads-format


# snippet:begin trace-id-filter
class TraceIdOrBlank(logging.Filter):
    """The fork and join lines belong to no span, so they carry no ``traceId``: print a blank
    rather than let the format raise."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__.setdefault("traceId", "")
        return True


# snippet:end trace-id-filter


def correlation_handler(line_format: str) -> logging.Handler:
    """A file handler (rewritten each run) for the ``narrativetrace`` logger and its children."""
    target = Path(os.environ[CORRELATION_LOG_FILE_ENV])
    target.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(target, mode="w", encoding="utf-8")
    handler.addFilter(TraceIdOrBlank())
    handler.setFormatter(logging.Formatter(line_format))
    return handler


def install(line_format: str) -> None:
    """Routes every ``narrativetrace*`` record, at DEBUG, to the correlation file."""
    logger = logging.getLogger("narrativetrace")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(correlation_handler(line_format))
