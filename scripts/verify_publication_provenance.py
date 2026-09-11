# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Post-publish PROVENANCE verification for `poe verify-publication` — the exact gap that let
the 0.1.0 release report green while four of its eight packages shipped with no PEP 740
attestation at all: the eight PyPI projects did not exist yet at first publish, so trusted
publishing could not be configured in time for that first upload, and PyPI never lets a version
already published without an attestation gain one after the fact. Mirrors
`narrative-trace-ts/tools/verify-publication-provenance.ts`'s shape, adapted to PyPI's own
Integrity API rather than npm's registry `dist.attestations` field — the two registries expose
provenance completely differently, so nothing below is a line-for-line port.

What this checks, per published file (`.whl` and `.tar.gz`):

1. The registry's own JSON metadata (`https://pypi.org/pypi/<name>/<version>/json`) names the
   file and its sha256 digest — ground truth for "what actually got uploaded". Never downloaded
   and re-hashed here: the registry already computed and serves this digest, and re-fetching
   whole distributions on every verification run would make this check far heavier than the
   presence poll it sits beside.
2. PyPI's Integrity API (`https://pypi.org/integrity/<name>/<version>/<filename>/provenance`) is
   queried for that exact file. A 404 with body `{"message": "No provenance available for
   ..."}` is not treated as an error — it is the honest, distinct `NOT_ATTESTED` verdict this
   check exists to surface, reported per package, never silently folded into a generic pass (see
   `PackageProvenanceReport.status`).
3. When attested, each attestation bundle's DSSE envelope carries a base64-encoded in-toto
   `Statement` (`envelope.statement`). Decoded and checked for `subject[0].name == filename`,
   `subject[0].digest.sha256` equal to the registry's own digest for that exact file (the
   attestation is bound to THESE bytes, not merely served next to them), and `predicateType ==
   PUBLISH_PREDICATE` (PyPI's own attestation kind — PyPI does not additionally mint the SLSA
   provenance attestation the npm-side `verify-publication-provenance.ts` also checks for, so
   only one predicate type is expected here, unlike that tool's `hasBothPredicates`).

## What this deliberately does NOT verify

Cryptographic signature / Sigstore certificate-chain (Fulcio) and Rekor transparency-log
inclusion-proof verification. The Integrity API response carries `verification_material
.certificate` and `.transparency_entries`, and neither is walked here. Doing that for real means
depending on the `sigstore` client's trust-root verification stack (a TUF-distributed root
bundle plus Merkle inclusion-proof checking against Rekor) or reimplementing a security-critical
library badly — the first is a real dependency this tool does not otherwise need, the second is
not a reasonable thing to hand-roll. What IS verified is attestation PRESENCE plus CONTENT-BINDING
(the attestation's subject name and digest match the exact file the registry actually serves for
this exact version) — never mistake that for a full chain verification; see
`PROVENANCE_SCOPE_NOTE`, printed in every report.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

DEFAULT_METADATA_BASE = "https://pypi.org/pypi"
DEFAULT_INTEGRITY_BASE = "https://pypi.org/integrity"
DEFAULT_FETCH_TIMEOUT_SECONDS = 20.0

# PyPI's own PEP 740 attestation kind (minted by `pypa/gh-action-pypi-publish` on every Trusted
# Publishing upload). Unlike npm's two-attestation pairing (publish + SLSA provenance), PyPI mints
# only this one — there is no second predicate type to require here.
PUBLISH_PREDICATE = "https://docs.pypi.org/attestations/publish/v1"

PROVENANCE_SCOPE_NOTE = (
    "cryptographic signature / Sigstore certificate-chain (Fulcio) and Rekor transparency-log "
    "inclusion-proof verification is NOT performed by this check (it would need the `sigstore` "
    "trust-root verification stack); this check asserts attestation PRESENCE on PyPI's Integrity "
    "API and CONTENT-BINDING (the attestation's subject name + sha256 digest match the file the "
    "registry actually serves for this exact version) — not a full chain verification."
)

Verdict = Literal["ATTESTED", "NOT_ATTESTED", "MISMATCH", "UNKNOWN"]
PackageStatus = Literal["ATTESTED", "NOT_ATTESTED", "PARTIAL", "UNKNOWN", "SKIPPED"]

# (status, parsed-JSON-body-or-None) — mirrors this package's own `default_fetch_status` split
# (verify_publication_registry.py) between the pure classifier and the network edge, except this
# API's 404 body carries information (`{"message": ...}`) worth keeping rather than discarding.
FetchJson = Callable[[str], tuple[int, object]]


class ProvenanceFetchError(RuntimeError):
    """A registry/integrity call failed in a way that is NOT the honest 'no provenance' 404 — a
    5xx, no response at all, or a malformed body where a well-formed one was required. Kept
    distinct from `NOT_ATTESTED` so a real outage is never misreported as an unattested release."""


def metadata_url(name: str, version: str, registry_base: str = DEFAULT_METADATA_BASE) -> str:
    """The legacy JSON API URL that carries every published file's name and digest for one
    package version."""
    return f"{registry_base}/{name}/{version}/json"


def integrity_url(
    name: str, version: str, filename: str, integrity_base: str = DEFAULT_INTEGRITY_BASE
) -> str:
    """PyPI's Integrity API URL for one exact published file's provenance."""
    return f"{integrity_base}/{name}/{version}/{filename}/provenance"


def default_fetch_json(url: str) -> tuple[int, object]:
    """GETs `url`, returning `(status, parsed_json_body)`. A non-2xx response still parses its
    JSON body when there is one — the Integrity API's 404s carry a `{"message": ...}` body that
    callers use to tell `NOT_ATTESTED` apart from a real fetch failure, so discarding it on a
    non-200 status (the way `default_fetch_status` discards bodies entirely) would lose exactly
    the information this check exists to report. `body` is `None` when there is none to parse or
    it did not parse as JSON."""
    try:
        with urlopen(url, timeout=DEFAULT_FETCH_TIMEOUT_SECONDS) as response:  # nosec B310 -
            # registry_base/integrity_base default to the fixed pypi.org hosts above; a caller
            # overriding them (e.g. a rehearsal against TestPyPI) is never untrusted input.
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return exc.code, None
    except URLError as exc:
        raise ProvenanceFetchError(f"GET {url} -> no response ({exc})") from exc


@dataclass(frozen=True)
class RegistryFile:
    """One published file's name and PyPI-computed sha256 digest, as the registry's own JSON
    metadata reports it — never re-derived by downloading and re-hashing the file."""

    filename: str
    sha256: str


def fetch_registry_files(
    name: str, version: str, fetch: FetchJson, registry_base: str = DEFAULT_METADATA_BASE
) -> tuple[RegistryFile, ...]:
    """Every file (`.whl`, `.tar.gz`, …) the registry lists for `name==version`, with the sha256
    digest PyPI itself computed at upload time. Raises `ProvenanceFetchError` on anything other
    than a clean 200 with a well-formed `urls` list — callers are expected to only call this once
    a presence check has already confirmed the version exists."""
    status, body = fetch(metadata_url(name, version, registry_base))
    if status != 200 or not isinstance(body, dict):
        raise ProvenanceFetchError(
            f"{name}=={version}: registry metadata fetch failed (HTTP {status})"
        )
    urls = body.get("urls")
    if not isinstance(urls, list) or not urls:
        raise ProvenanceFetchError(f"{name}=={version}: registry metadata has no published files")
    files: list[RegistryFile] = []
    for entry in urls:
        filename = entry.get("filename") if isinstance(entry, dict) else None
        digests = entry.get("digests") if isinstance(entry, dict) else None
        sha256 = digests.get("sha256") if isinstance(digests, dict) else None
        if not isinstance(filename, str) or not isinstance(sha256, str):
            raise ProvenanceFetchError(
                f"{name}=={version}: a registry file entry is missing filename or sha256 digest"
            )
        files.append(RegistryFile(filename=filename, sha256=sha256))
    return tuple(files)


def _decode_statement(payload_b64: str) -> dict[str, object] | None:
    """Decodes one DSSE envelope's base64 in-toto `Statement` payload. `None` on anything
    malformed — a bad payload is a `MISMATCH`, never a crash."""
    try:
        raw = base64.b64decode(payload_b64, validate=False)
        parsed = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _statements_in(integrity_body: dict[str, object]) -> list[dict[str, object]]:
    bundles = integrity_body.get("attestation_bundles")
    if not isinstance(bundles, list):
        return []
    statements: list[dict[str, object]] = []
    for bundle in bundles:
        attestations = bundle.get("attestations") if isinstance(bundle, dict) else None
        if not isinstance(attestations, list):
            continue
        for attestation in attestations:
            envelope = attestation.get("envelope") if isinstance(attestation, dict) else None
            payload = envelope.get("statement") if isinstance(envelope, dict) else None
            if isinstance(payload, str):
                statement = _decode_statement(payload)
                if statement is not None:
                    statements.append(statement)
    return statements


def _predicate_type(statement: dict[str, object]) -> str | None:
    predicate_type = statement.get("predicateType")
    return predicate_type if isinstance(predicate_type, str) else None


def _subject_of(statement: dict[str, object]) -> dict[str, object] | None:
    """The statement's first subject, typed as a plain `dict` so callers never re-index an
    `object` (mypy strict rejects that) — in-toto statements carry a `subject` list, but this
    check only ever compares against one file per attestation."""
    subjects = statement.get("subject")
    if not isinstance(subjects, list) or not subjects:
        return None
    first = subjects[0]
    return first if isinstance(first, dict) else None


def _subject_sha256(subject: dict[str, object]) -> str | None:
    digest = subject.get("digest")
    sha256 = digest.get("sha256") if isinstance(digest, dict) else None
    return sha256 if isinstance(sha256, str) else None


@dataclass(frozen=True)
class FileProvenanceCheck:
    """The provenance verdict for one published file."""

    filename: str
    verdict: Verdict
    predicate_types_found: tuple[str, ...] = ()
    subject_name_matches: bool = False
    digest_matches: bool = False
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict == "ATTESTED"


def evaluate_file_provenance(
    registry_file: RegistryFile, integrity_status: int, integrity_body: object
) -> FileProvenanceCheck:
    """Classifies one file's Integrity API response against the registry's own digest for it.
    Pure — network access lives in `default_fetch_json`/`check_package_provenance` only, so this
    is unit-testable against fixed status/body pairs, the same split every other
    `verify_publication_*` module in this repository uses."""
    if integrity_status == 404:
        return FileProvenanceCheck(
            filename=registry_file.filename,
            verdict="NOT_ATTESTED",
            detail="PyPI's Integrity API has no provenance for this file — published without a "
            "PEP 740 attestation (e.g. a pre-trusted-publishing bootstrap-token upload).",
        )
    if integrity_status != 200 or not isinstance(integrity_body, dict):
        return FileProvenanceCheck(
            filename=registry_file.filename,
            verdict="UNKNOWN",
            detail=f"Integrity API returned HTTP {integrity_status} — not a clean "
            "attested/not-attested answer.",
        )
    statements = _statements_in(integrity_body)
    if not statements:
        return FileProvenanceCheck(
            filename=registry_file.filename,
            verdict="UNKNOWN",
            detail="Integrity API returned 200 but no decodable attestation statement.",
        )

    predicate_types_found = tuple(
        pt for pt in (_predicate_type(s) for s in statements) if pt is not None
    )
    subjects = [s for s in (_subject_of(statement) for statement in statements) if s is not None]
    subject_name_matches = bool(subjects) and all(
        subject.get("name") == registry_file.filename for subject in subjects
    )
    digest_matches = bool(subjects) and all(
        _subject_sha256(subject) == registry_file.sha256 for subject in subjects
    )
    ok = subject_name_matches and digest_matches and PUBLISH_PREDICATE in predicate_types_found
    detail = (
        f"{len(statements)} attestation(s), subject name + sha256 digest both bound to the "
        "published file"
        if ok
        else f"mismatch — predicates={list(predicate_types_found)} "
        f"subject_name_matches={subject_name_matches} digest_matches={digest_matches}"
    )
    return FileProvenanceCheck(
        filename=registry_file.filename,
        verdict="ATTESTED" if ok else "MISMATCH",
        predicate_types_found=predicate_types_found,
        subject_name_matches=subject_name_matches,
        digest_matches=digest_matches,
        detail=detail,
    )


@dataclass(frozen=True)
class PackageProvenanceReport:
    """The provenance verdict for one package version, rolled up from its published files. A
    package without provenance is always a distinct, visible `NOT_ATTESTED` — see `status` — not
    a silent pass, which is the exact gap that let the 0.1.0 release report green while half its
    packages shipped unattested."""

    name: str
    version: str
    files: tuple[FileProvenanceCheck, ...] = ()
    skipped_reason: str | None = None

    @property
    def status(self) -> PackageStatus:
        if self.skipped_reason is not None:
            return "SKIPPED"
        if not self.files:
            return "UNKNOWN"
        verdicts = {f.verdict for f in self.files}
        if verdicts == {"ATTESTED"}:
            return "ATTESTED"
        if verdicts == {"NOT_ATTESTED"}:
            return "NOT_ATTESTED"
        if verdicts <= {"UNKNOWN"}:
            return "UNKNOWN"
        return "PARTIAL"

    @property
    def ok(self) -> bool:
        """`True` when this package needs no attention: fully attested, or deliberately skipped
        (not yet published at this version — see `skipped_provenance_report`). `NOT_ATTESTED`,
        `PARTIAL`, and `UNKNOWN` are all findings, never folded into a pass."""
        return self.status in ("ATTESTED", "SKIPPED")


def skipped_provenance_report(name: str, version: str, reason: str) -> PackageProvenanceReport:
    """A package this run deliberately did not check — mirrors `SmokeResult`'s `SKIPPED` verdict
    (`verify_publication_smoke.py`): querying provenance for a version the presence poll has not
    confirmed PRESENT would fail on an ordinary 404, which is a true statement but the wrong one."""
    return PackageProvenanceReport(name=name, version=version, skipped_reason=reason)


def check_package_provenance(
    name: str,
    version: str,
    fetch: FetchJson,
    registry_base: str = DEFAULT_METADATA_BASE,
    integrity_base: str = DEFAULT_INTEGRITY_BASE,
) -> PackageProvenanceReport:
    """Checks every published file of `name==version` for a bound PEP 740 attestation. Raises
    `ProvenanceFetchError` if the registry metadata itself cannot be read — callers only reach
    that once presence is already confirmed, so it signals a real outage, not an unpublished
    version."""
    files = fetch_registry_files(name, version, fetch, registry_base)
    checks = []
    for registry_file in files:
        url = integrity_url(name, version, registry_file.filename, integrity_base)
        status, body = fetch(url)
        checks.append(evaluate_file_provenance(registry_file, status, body))
    return PackageProvenanceReport(name=name, version=version, files=tuple(checks))
