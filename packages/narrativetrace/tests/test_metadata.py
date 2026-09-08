# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for request/user metadata wrappers and ServiceIdentity."""

import pytest

from narrativetrace.metadata import (
    ClientIp,
    EnduserId,
    HttpRoute,
    ServiceIdentity,
    SessionId,
    TenantId,
    _StringWrapper,
)

WRAPPERS: list[type[_StringWrapper]] = [HttpRoute, ClientIp, EnduserId, SessionId, TenantId]


@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_wrapper_is_transparent_in_string_context(wrapper: type[_StringWrapper]) -> None:
    assert str(wrapper.of("v")) == "v"
    assert wrapper.of("v").value == "v"


@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_wrapper_rejects_none(wrapper: type[_StringWrapper]) -> None:
    with pytest.raises((ValueError, TypeError)):
        wrapper.of(None)  # type: ignore[arg-type]


@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_wrapper_equality(wrapper: type[_StringWrapper]) -> None:
    assert wrapper.of("a") == wrapper.of("a")
    assert wrapper.of("a") != wrapper.of("b")


def test_service_identity_fields() -> None:
    identity = ServiceIdentity("order-service", "1.2.3", "production")
    assert identity.service_name == "order-service"
    assert identity.service_version == "1.2.3"
    assert identity.environment == "production"
