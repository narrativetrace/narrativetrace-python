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


_ENV_NAME = "NARRATIVETRACE_SERVICE_NAME"
_ENV_VERSION = "NARRATIVETRACE_SERVICE_VERSION"
_ENV_ENVIRONMENT = "NARRATIVETRACE_ENVIRONMENT"


class TestServiceIdentityFromEnvironment:
    def test_all_three_keys_are_read(self) -> None:
        env = {_ENV_NAME: "orders", _ENV_VERSION: "1.2.3", _ENV_ENVIRONMENT: "prod"}
        assert ServiceIdentity.from_environment(env) == ServiceIdentity("orders", "1.2.3", "prod")

    def test_only_a_name_leaves_version_and_environment_unset(self) -> None:
        identity = ServiceIdentity.from_environment({_ENV_NAME: "orders"})
        assert identity == ServiceIdentity("orders", None, None)

    @pytest.mark.parametrize("env", [{}, {_ENV_NAME: ""}, {_ENV_NAME: "   "}])
    def test_no_usable_name_means_no_identity(self, env: dict[str, str]) -> None:
        assert ServiceIdentity.from_environment(env) is None

    def test_version_without_a_name_is_not_an_identity(self) -> None:
        assert ServiceIdentity.from_environment({_ENV_VERSION: "1.2.3"}) is None

    def test_blank_version_and_environment_are_unset(self) -> None:
        env = {_ENV_NAME: "orders", _ENV_VERSION: " ", _ENV_ENVIRONMENT: ""}
        assert ServiceIdentity.from_environment(env) == ServiceIdentity("orders", None, None)

    def test_the_process_environment_is_the_default_source(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(_ENV_NAME, "from-process")
        identity = ServiceIdentity.from_environment()
        assert identity is not None
        assert identity.service_name == "from-process"
