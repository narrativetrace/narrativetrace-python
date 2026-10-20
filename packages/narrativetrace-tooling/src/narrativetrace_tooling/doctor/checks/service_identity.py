# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``config.service-identity`` — non-test source builds a context but nobody names the service, so
every trace says ``unknown_service:python`` on the platform and in OpenTelemetry.

The service is named by ``NARRATIVETRACE_SERVICE_NAME`` in the environment or by
``ContextVarNarrativeContext(service_identity=ServiceIdentity("orders"))`` in source. The check
reads text only — it never imports or parses the project's code — and looks for either anywhere in
the project, so a context built in one module and an identity defined in another still pass. Test
source is ignored: a test's trace is not a service."""

from __future__ import annotations

import re
from collections.abc import Mapping

from narrativetrace_tooling.doctor.doc_urls import DOC
from narrativetrace_tooling.doctor.finding import failed, passed
from narrativetrace_tooling.doctor.types import DoctorSnapshot, Finding

ID = "config.service-identity"

_ENV_KEY = "NARRATIVETRACE_SERVICE_NAME"
_BUILDS_CONTEXT = re.compile(r"\bContextVarNarrativeContext\s*\(")
_NAMES_SERVICE = re.compile(r"\bServiceIdentity\s*\(|\bservice_identity\s*=")
_TEST_PATH = re.compile(r"(?:^|/)(?:tests?/|test_[^/]*$|[^/]*_test\.py$|conftest\.py$)")
_FIX = (
    "Name the service so its traces stop reading unknown_service:python: set "
    f"{_ENV_KEY}=orders (and NARRATIVETRACE_SERVICE_VERSION, NARRATIVETRACE_ENVIRONMENT) in the "
    "environment the service runs in, or pass "
    'ContextVarNarrativeContext(service_identity=ServiceIdentity("orders")).'
)


def _non_test_python(snapshot: DoctorSnapshot) -> Mapping[str, str]:
    return {
        path: content
        for path, content in snapshot.source_files.items()
        if path.endswith(".py") and not _TEST_PATH.search(path)
    }


def check_service_identity(snapshot: DoctorSnapshot) -> Finding:
    if snapshot.env.get(_ENV_KEY, "").strip():
        return passed(ID, f"{_ENV_KEY} names the service", DOC["service_identity"])
    source = _non_test_python(snapshot)
    if any(_NAMES_SERVICE.search(content) for content in source.values()):
        return passed(ID, "the source passes a ServiceIdentity", DOC["service_identity"])
    builder = next((path for path, text in source.items() if _BUILDS_CONTEXT.search(text)), None)
    if builder is None:
        return passed(ID, "no non-test source builds a context yet", DOC["service_identity"])
    message = (
        f"{builder} builds a context but no service name is set, so traces say "
        "unknown_service:python"
    )
    return failed(ID, message, _FIX, DOC["service_identity"])
