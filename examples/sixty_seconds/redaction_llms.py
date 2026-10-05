# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# test_redaction.py
from narrativetrace import IndentedTextRenderer, trace_object


class PaymentService:
    def charge_card(self, payment_token, amount):
        return "captured"


def test_deny_listed_parameter_is_redacted(narrative_trace):
    service = trace_object(PaymentService(), narrative_trace)
    service.charge_card("tok_live_4242", 1999)

    rendered = IndentedTextRenderer().render(narrative_trace.capture_trace())

    assert "[REDACTED]" in rendered
    assert "1999" in rendered
