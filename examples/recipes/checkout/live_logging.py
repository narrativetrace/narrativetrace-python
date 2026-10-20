# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Live logging for the recipe scenarios that need the lines as the calls happen.

``export_to_logger`` replays a finished trace on one thread; the cross-service and cross-thread
recipes are about *which* thread and *which* service wrote a line, so their contexts hand every
event to a ``LoggingTraceConsumer`` the moment it is published -- the live path the Logging Guide
describes.
"""

from __future__ import annotations

import logging

from narrativetrace import LoggingTraceConsumer, TraceEvent
from narrativetrace.pipeline.event_store import EventStore


class LoggingEventStore(EventStore):
    """Logs every event as it happens, and keeps it for ``capture_trace()``."""

    def __init__(self, logger: logging.Logger) -> None:
        super().__init__()
        self._consumer = LoggingTraceConsumer(logger)

    def add(self, event: TraceEvent) -> None:
        self._consumer.accept(event)
        super().add(event)
