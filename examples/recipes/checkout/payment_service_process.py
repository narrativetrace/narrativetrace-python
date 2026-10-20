# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The second service of documentation/recipes/follow-one-request-across-services.md.

A loopback HTTP server in the same process: the request really crosses a socket and the
``traceparent`` really arrives as a header, which is what the page is about. A second process would
add a second interpreter and prove nothing further.
"""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import TracebackType

from narrativetrace_asgi import parse_traceparent

from examples.recipes.checkout.domain import PaymentDeclinedError
from examples.recipes.checkout.live_logging import LoggingEventStore
from examples.recipes.checkout.services import PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceTree, trace_object

LOGGER_NAME = "narrativetrace.payments"


class PaymentServiceProcess:
    """A traced payment service on a loopback port, with a narrative context of its own."""

    def __init__(self) -> None:
        # snippet:begin own-context
        self.context = ContextVarNarrativeContext(
            store=LoggingEventStore(logging.getLogger(LOGGER_NAME))
        )
        self._payments = trace_object(PaymentService(), self.context)
        # snippet:end own-context
        self.inbound_traceparent: str | None = None
        self.last_trace: TraceTree | None = None
        self._server = HTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="payment-service", daemon=True
        )

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/charge"

    def __enter__(self) -> PaymentServiceProcess:
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                service.handle(self)

            def log_message(self, format: str, *args: object) -> None:
                """Silences http.server's stderr access log."""

        return Handler

    # snippet:begin inbound
    def handle(self, exchange: BaseHTTPRequestHandler) -> None:
        header = exchange.headers.get("traceparent")
        self.inbound_traceparent = header
        self.context.reset()
        parsed = parse_traceparent(header)
        if parsed is not None:
            self.context.adopt_trace_id(parsed.trace_id, parsed.span_id)
        try:
            length = int(exchange.headers["Content-Length"])
            customer_id, amount_cents, card = exchange.rfile.read(length).decode().split(",", 2)
            reply(exchange, 200, self._payments.charge(customer_id, int(amount_cents), card))
        except PaymentDeclinedError as declined:
            reply(exchange, 402, str(declined))
        finally:
            self.last_trace = self.context.capture_trace()
            self.context.reset()
            # snippet:end inbound


def reply(exchange: BaseHTTPRequestHandler, status: int, body: str) -> None:
    payload = body.encode()
    exchange.send_response(status)
    exchange.send_header("Content-Length", str(len(payload)))
    exchange.end_headers()
    exchange.wfile.write(payload)
