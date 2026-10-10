# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from payments import PaymentService

from narrativetrace import (
    REDACTED_MARKER,
    ContextVarNarrativeContext,
    IndentedTextRenderer,
    trace_object,
)


def test_the_auth_token_is_redacted_and_the_other_arguments_survive() -> None:
    context = ContextVarNarrativeContext()
    service = trace_object(PaymentService(), context)

    service.charge("C-1234", "secret-token-value", "42.00")

    rendered = IndentedTextRenderer().render(context.capture_trace())
    assert REDACTED_MARKER in rendered
    assert "secret-token-value" not in rendered
    assert "C-1234" in rendered
