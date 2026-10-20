# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``config.exclude`` — reports the effective exclusion list (list 2) a project resolves to, and
fails when a configured ``exclude`` value is malformed.

The list itself is resolved by the ``narrativetrace`` distribution (this package cannot import it)
and arrives on the snapshot: ``effective_exclude`` is the resolved module prefixes,
``exclude_source`` says whether they are the shipped default or came from the environment or a
config file, and ``exclude_error`` carries the message of a value that would not parse. A malformed
configured value never reaches the host's call (the shipped default applies there), so the doctor
is where it becomes visible."""

from __future__ import annotations

from narrativetrace_tooling.doctor.doc_urls import DOC
from narrativetrace_tooling.doctor.finding import failed, passed
from narrativetrace_tooling.doctor.types import DoctorSnapshot, Finding

ID = "config.exclude"


def check_exclude(snapshot: DoctorSnapshot) -> Finding:
    if snapshot.exclude_error is not None:
        return failed(
            ID,
            f"the exclude setting is malformed: {snapshot.exclude_error}",
            "Give exclude as ';'-delimited dotted module names (e.g. 'acme.mocks;acme.fakes'), "
            "each at most once, in NARRATIVETRACE_EXCLUDE or the 'exclude' key. Until it is fixed "
            "the shipped default list applies.",
            DOC["exclude"],
        )
    prefixes = snapshot.effective_exclude
    if prefixes is None:
        return passed(ID, "no exclude list was resolved for this snapshot", DOC["exclude"])
    count = f"{len(prefixes)} module{'' if len(prefixes) == 1 else 's'}"
    listing = ", ".join(prefixes) if prefixes else "nothing is excluded by module name"
    origin = (
        "the shipped default"
        if snapshot.exclude_source == "default"
        else "configured, replacing the shipped default"
    )
    return passed(ID, f"effective exclude list is {origin} ({count}): {listing}", DOC["exclude"])
