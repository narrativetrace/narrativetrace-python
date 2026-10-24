# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A tracer-provider helper that installs NarrativeTrace span-id mirroring by default.

``tracer_provider(**kwargs)`` builds ``TracerProvider(id_generator=NarrativeTraceIdGenerator(),
**kwargs)``, so an application that builds its provider through it gets mirrored ids without
writing the one-liner. Every other keyword passes to ``TracerProvider`` unchanged.

Edge cases: an ``id_generator`` the caller passes is kept, with one warning that ids will not
mirror. ``mirror_ids=False`` or ``NARRATIVETRACE_OTEL_MIRROR_IDS=false`` opts out and builds a
plain provider. ``set_global=True`` also registers the provider with
``opentelemetry.trace.set_tracer_provider``.

The OpenTelemetry SDK is imported when the function runs, so importing this package still needs
only ``opentelemetry-api``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider

_LOG = logging.getLogger("narrativetrace_otel")


def tracer_provider(
    *, mirror_ids: bool | None = None, set_global: bool = False, **kwargs: Any
) -> TracerProvider:
    """Builds a ``TracerProvider`` with the NarrativeTrace id generator installed.

    ``mirror_ids=None`` reads the ``NARRATIVETRACE_OTEL_MIRROR_IDS`` opt-out; ``False`` opts out.
    """
    from opentelemetry import trace  # noqa: PLC0415
    from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415

    from narrativetrace_otel.id_generator import (  # noqa: PLC0415
        NarrativeTraceIdGenerator,
        mirror_ids_enabled,
    )

    enabled = mirror_ids_enabled() if mirror_ids is None else mirror_ids
    if enabled:
        if kwargs.get("id_generator") is not None:
            _LOG.warning(
                "NarrativeTrace: tracer_provider() was given its own id_generator, which is "
                "kept; span ids will not mirror NarrativeTrace's. Pass "
                "NarrativeTraceIdGenerator(delegate) as that generator to have both."
            )
        else:
            kwargs["id_generator"] = NarrativeTraceIdGenerator()
    provider = TracerProvider(**kwargs)
    if set_global:
        trace.set_tracer_provider(provider)
    return provider
