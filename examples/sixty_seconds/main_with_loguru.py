# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# main.py
import inspect  # new: InterceptHandler's own frame-walk, verbatim from Loguru's recipe
import logging  # new: the stdlib logger InterceptHandler subclasses; export_to_logger's target
import sys  # new: stdout target for the loguru sink below

from loguru import logger  # new: the destination sink

from narrativetrace import (
    ContextVarNarrativeContext,
    IndentedTextRenderer,
    TraceId,
    export_to_logger,  # new: replays an already-captured trace through your logger, one call
    trace_object,
)


class OrderService:
    def place_order(self, customer_id, product_id, quantity):
        return f"ORD-{customer_id}-{product_id}-{quantity}"


# snippet:begin fixedTraceId
# A fixed trace id, adopted so this page's embedded output always names the same trace. A real
# run generates a random one every time (never this -- it is this DEMO's own constant, not the
# library default) via the same TraceId.adopt_trace_id a servlet-style boundary uses for an
# inbound trace header.
DEMO_TRACE_ID = TraceId("a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4")

# snippet:end fixedTraceId


# snippet:begin interceptHandler
# new: Loguru's own documented stdlib-interop recipe, verbatim -- see
# https://loguru.readthedocs.io/en/stable/overview.html, "Entirely compatible with standard
# logging". NarrativeTrace ships no Loguru-specific bridge; this recipe is the whole mechanism --
# every record a stdlib logger emits (export_to_logger's included) is re-logged through `logger`.
class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists.
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message.
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# snippet:end interceptHandler

# new: a fixed, timestamp-free sink so this page's embedded output never varies by wall clock --
# your own sink keeps its real format, colours, and rotation; only this demo needs determinism.
logger.remove()
logger.add(sys.stdout, format="{level} | {message}", colorize=False)
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

context = ContextVarNarrativeContext()
context.adopt_trace_id(DEMO_TRACE_ID)
service = trace_object(OrderService(), context)
service.place_order("cust-1", "prod-42", 3)

trace = context.capture_trace()  # new: capture once, reuse for both the print and the export
print(IndentedTextRenderer().render(trace))

export_to_logger(trace)  # new: the same one-call export from step 2 -- now landing in Loguru
