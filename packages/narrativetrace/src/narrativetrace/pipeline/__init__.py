# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Event pipeline: buffered, bounded, fail-safe event routing and retention.

The Java ``narrativetrace-core`` pipeline package. ``observability failure never becomes an
application failure`` is the guiding invariant. Multi-invocation aggregation was relocated to the
paid tier per Phase 31a (2026-07-12).
"""

from narrativetrace.pipeline.bounded_buffer import BoundedEventBuffer
from narrativetrace.pipeline.buffered_consumer import DEFAULT_CAPACITY, BufferedEventConsumer
from narrativetrace.pipeline.dual_path import DualPathPipeline
from narrativetrace.pipeline.event_store import EventStore
from narrativetrace.pipeline.perishable import PerishableMap
from narrativetrace.pipeline.subscriber import EventStoreSubscriber

__all__ = [
    "DEFAULT_CAPACITY",
    "BoundedEventBuffer",
    "BufferedEventConsumer",
    "DualPathPipeline",
    "EventStore",
    "EventStoreSubscriber",
    "PerishableMap",
]
