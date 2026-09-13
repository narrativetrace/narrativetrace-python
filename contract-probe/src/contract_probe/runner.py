# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The standalone runner behind `contract-probe` (docs-vs-published-gate §2) -- reads
`documentation/contract.yaml`, decides which entries apply at the installed version (ruling 1:
exempt only while `since` is strictly later than installed), runs the applicable ones' dispatched
probe against a PUBLISHED install (never `mavenLocal`/workspace-equivalent, never `--find-links`),
and prints holds/fails/not-applicable-before-since per entry plus one summary line. Writes a JSON
result when `--out` is given. Exits 1 on any FAILS -- the signal `scripts/contract_check.py` (the
nightly wrapper) keys off.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

from contract_probe.args import Args, parse
from contract_probe.contract_yaml import ContractEntry, read
from contract_probe.probes import (
    approval_default_probe,
    entry_point_probe,
    export_to_logger_probe,
    logging_consumer_depth_probe,
    manifest_identity_probe,
    native_stringification_not_trusted_probe,
    not_traced_class_attribute_probe,
    platform_type_carveout_probe,
    pytest_artifacts_default_probe,
    structlog_dependency_probe,
    typed_error_marker_probe,
)
from contract_probe.versions import is_applicable

_ENTRY_POINT_IDS = frozenset(
    {
        "entry-point-narrativetrace",
        "entry-point-narrativetrace-pytest",
        "entry-point-narrativetrace-diagrams",
        "entry-point-narrativetrace-otel",
        "entry-point-narrativetrace-asgi",
        "entry-point-narrativetrace-clarity",
        "entry-point-narrativetrace-structlog",
        "entry-point-narrativetrace-glossary",
    }
)

_DISPATCH: dict[str, Callable[[], str]] = {
    "probed-not-traced-class-attribute": not_traced_class_attribute_probe.observe,
    "probed-pytest-artifacts-default": pytest_artifacts_default_probe.observe,
    "config-shape-export-to-logger": export_to_logger_probe.observe,
    "config-shape-logging-consumer-per-instance-depth": logging_consumer_depth_probe.observe,
    "reflectable-structlog-depends-on-structlog": structlog_dependency_probe.observe,
    "probed-native-stringification-not-trusted": native_stringification_not_trusted_probe.observe,
    "probed-platform-type-carveout": platform_type_carveout_probe.observe,
    "probed-typed-error-marker": typed_error_marker_probe.observe,
    "probed-approval-default": approval_default_probe.observe,
    "probed-manifest-per-invocation-identity": manifest_identity_probe.observe,
}


def _observe(entry: ContractEntry, version: str) -> str:
    if entry.id in _ENTRY_POINT_IDS:
        return entry_point_probe.observe(entry.coordinate or entry.id, version)
    dispatch = _DISPATCH.get(entry.id)
    if dispatch is None:
        raise RuntimeError(
            f'no probe dispatch registered for entry "{entry.id}" -- add one in runner._DISPATCH'
        )
    return dispatch()


def _failure_message(entry: ContractEntry, installed_version: str, observed: str | None) -> str:
    coordinate = entry.coordinate or entry.id
    shown = observed if observed is not None else "<no answer>"
    return (
        f'documentation/contract.yaml: {entry.id} documented default "{entry.expect}" '
        f'(since {entry.since}) but {coordinate} {installed_version} (published) reads "{shown}"'
    )


def _entry_outcome(entry: ContractEntry, version: str) -> tuple[str, str]:
    if not is_applicable(entry.since, version):
        return (
            "not-applicable-before-since",
            f"since {entry.since} is later than installed {version}",
        )
    observed = _observe(entry, version)
    if observed == entry.expect:
        return "holds", f'observed "{observed}"'
    return "fails", _failure_message(entry, version, observed)


def run(args: Args) -> int:
    entries = read(Path(args.contract_path))
    counts = {"holds": 0, "not-applicable-before-since": 0, "fails": 0}
    json_entries: list[dict[str, str]] = []

    for entry in entries:
        verdict, detail = _entry_outcome(entry, args.version)
        counts[verdict] += 1
        print(f"{entry.id:<50} {verdict:<30} {detail}")
        json_entries.append(
            {
                "id": entry.id,
                "kind": entry.kind,
                "since": entry.since,
                "verdict": verdict,
                "detail": detail,
            }
        )

    summary = (
        f"{counts['holds']} holds, {counts['not-applicable-before-since']} "
        f"not-applicable-before-since, {counts['fails']} fails (installed version {args.version})"
    )
    print()
    print(summary)

    if args.out_path is not None:
        payload = {
            "version": args.version,
            "entries": json_entries,
            "summary": {
                "holds": counts["holds"],
                "notApplicableBeforeSince": counts["not-applicable-before-since"],
                "fails": counts["fails"],
            },
        }
        Path(args.out_path).write_text(json.dumps(payload), encoding="utf-8")

    return 1 if counts["fails"] > 0 else 0


def main() -> int:
    return run(parse(sys.argv[1:]))


if __name__ == "__main__":
    sys.exit(main())
