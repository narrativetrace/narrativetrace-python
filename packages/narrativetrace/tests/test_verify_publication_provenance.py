# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pure-logic tests for `scripts/verify_publication_provenance.py`.

`default_fetch_json`'s real network call is exercised for real by `poe verify-publication`
against the live pypi.org Integrity API (see the tool's own report); these tests drive the
classification logic — the part that decides ATTESTED / NOT_ATTESTED / MISMATCH / UNKNOWN — against
fixed, injected (status, body) pairs shaped exactly like the real API's responses (see the module
docstring's worked example and this repository's own `poe verify-publication` run against the live
0.1.0 release, which is where these response shapes were taken from).
"""

from __future__ import annotations

import base64
import json

from scripts.verify_publication_provenance import (
    PUBLISH_PREDICATE,
    ProvenanceFetchError,
    RegistryFile,
    check_package_provenance,
    evaluate_file_provenance,
    fetch_registry_files,
    integrity_url,
    metadata_url,
    skipped_provenance_report,
)

FILENAME = "narrativetrace-0.1.1-py3-none-any.whl"
SHA256 = "83fc199b11adcea37161366ccd1af67e5d151827be74c869d432ff07138e7940"


def _encode_statement(**overrides: object) -> str:
    statement: dict[str, object] = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": FILENAME, "digest": {"sha256": SHA256}}],
        "predicateType": PUBLISH_PREDICATE,
        "predicate": None,
    }
    statement.update(overrides)
    return base64.b64encode(json.dumps(statement).encode("utf-8")).decode("ascii")


def _bundle_body(*statements_b64: str) -> dict[str, object]:
    return {
        "attestation_bundles": [
            {
                "attestations": [{"envelope": {"statement": s}} for s in statements_b64],
                "publisher": {"kind": "GitHub"},
            }
        ],
        "version": 1,
    }


class TestUrls:
    def test_metadata_url_names_the_exact_version(self) -> None:
        assert (
            metadata_url("narrativetrace", "0.1.1", "https://pypi.org/pypi")
            == "https://pypi.org/pypi/narrativetrace/0.1.1/json"
        )

    def test_integrity_url_names_the_exact_file(self) -> None:
        assert (
            integrity_url("narrativetrace", "0.1.1", FILENAME, "https://pypi.org/integrity")
            == f"https://pypi.org/integrity/narrativetrace/0.1.1/{FILENAME}/provenance"
        )


class TestEvaluateFileProvenance:
    REGISTRY_FILE = RegistryFile(filename=FILENAME, sha256=SHA256)

    def test_404_is_not_attested(self) -> None:
        check = evaluate_file_provenance(
            self.REGISTRY_FILE, 404, {"message": f"No provenance available for {FILENAME}"}
        )
        assert check.verdict == "NOT_ATTESTED"
        assert not check.ok

    def test_matching_subject_and_digest_is_attested(self) -> None:
        body = _bundle_body(_encode_statement())
        check = evaluate_file_provenance(self.REGISTRY_FILE, 200, body)
        assert check.verdict == "ATTESTED"
        assert check.ok
        assert check.subject_name_matches
        assert check.digest_matches
        assert check.predicate_types_found == (PUBLISH_PREDICATE,)

    def test_wrong_digest_is_a_mismatch_not_a_silent_pass(self) -> None:
        wrong_digest = {"name": FILENAME, "digest": {"sha256": "0" * 64}}
        body = _bundle_body(_encode_statement(subject=[wrong_digest]))
        check = evaluate_file_provenance(self.REGISTRY_FILE, 200, body)
        assert check.verdict == "MISMATCH"
        assert not check.ok
        assert check.subject_name_matches
        assert not check.digest_matches

    def test_wrong_subject_name_is_a_mismatch(self) -> None:
        wrong_name = {"name": "some-other-file.whl", "digest": {"sha256": SHA256}}
        body = _bundle_body(_encode_statement(subject=[wrong_name]))
        check = evaluate_file_provenance(self.REGISTRY_FILE, 200, body)
        assert check.verdict == "MISMATCH"
        assert not check.subject_name_matches

    def test_wrong_predicate_type_is_a_mismatch(self) -> None:
        body = _bundle_body(_encode_statement(predicateType="https://example.com/not-pypi/v1"))
        check = evaluate_file_provenance(self.REGISTRY_FILE, 200, body)
        assert check.verdict == "MISMATCH"
        assert check.predicate_types_found == ("https://example.com/not-pypi/v1",)

    def test_200_with_no_attestation_bundles_is_unknown(self) -> None:
        check = evaluate_file_provenance(self.REGISTRY_FILE, 200, {"attestation_bundles": []})
        assert check.verdict == "UNKNOWN"

    def test_malformed_base64_statement_is_unknown_not_a_crash(self) -> None:
        body = _bundle_body("not-valid-base64!!!")
        check = evaluate_file_provenance(self.REGISTRY_FILE, 200, body)
        assert check.verdict == "UNKNOWN"

    def test_a_server_error_is_unknown_never_silently_attested(self) -> None:
        check = evaluate_file_provenance(self.REGISTRY_FILE, 500, None)
        assert check.verdict == "UNKNOWN"


class TestFetchRegistryFiles:
    def test_parses_every_published_file_and_its_digest(self) -> None:
        def fetch(_url: str) -> tuple[int, object]:
            return 200, {
                "urls": [
                    {"filename": "a.whl", "digests": {"sha256": "aaa"}},
                    {"filename": "a.tar.gz", "digests": {"sha256": "bbb"}},
                ]
            }

        files = fetch_registry_files("narrativetrace", "0.1.1", fetch)

        assert files == (
            RegistryFile(filename="a.whl", sha256="aaa"),
            RegistryFile(filename="a.tar.gz", sha256="bbb"),
        )

    def test_non_200_status_raises(self) -> None:
        try:
            fetch_registry_files("narrativetrace", "0.1.1", lambda _url: (404, None))
        except ProvenanceFetchError as exc:
            assert "HTTP 404" in str(exc)
        else:
            raise AssertionError("expected ProvenanceFetchError")

    def test_a_file_entry_missing_a_digest_raises(self) -> None:
        def fetch(_url: str) -> tuple[int, object]:
            return 200, {"urls": [{"filename": "a.whl", "digests": {}}]}

        try:
            fetch_registry_files("narrativetrace", "0.1.1", fetch)
        except ProvenanceFetchError as exc:
            assert "missing filename or sha256" in str(exc)
        else:
            raise AssertionError("expected ProvenanceFetchError")


class TestCheckPackageProvenance:
    def test_all_files_attested_rolls_up_to_attested(self) -> None:
        def fetch(url: str) -> tuple[int, object]:
            if url.endswith("/json"):
                return 200, {"urls": [{"filename": FILENAME, "digests": {"sha256": SHA256}}]}
            return 200, _bundle_body(_encode_statement())

        report = check_package_provenance("narrativetrace", "0.1.1", fetch)

        assert report.status == "ATTESTED"
        assert report.ok

    def test_all_files_not_attested_rolls_up_to_not_attested(self) -> None:
        def fetch(url: str) -> tuple[int, object]:
            if url.endswith("/json"):
                return 200, {"urls": [{"filename": FILENAME, "digests": {"sha256": SHA256}}]}
            return 404, {"message": "No provenance available"}

        report = check_package_provenance("narrativetrace-glossary", "0.1.0", fetch)

        assert report.status == "NOT_ATTESTED"
        assert not report.ok  # distinct, visible finding -- never a silent pass

    def test_mixed_files_roll_up_to_partial(self) -> None:
        calls = iter([(200, _bundle_body(_encode_statement())), (404, {"message": "no"})])

        def fetch(url: str) -> tuple[int, object]:
            if url.endswith("/json"):
                return 200, {
                    "urls": [
                        {"filename": FILENAME, "digests": {"sha256": SHA256}},
                        {
                            "filename": "narrativetrace-0.1.1.tar.gz",
                            "digests": {"sha256": "c" * 64},
                        },
                    ]
                }
            return next(calls)

        report = check_package_provenance("narrativetrace", "0.1.1", fetch)

        assert report.status == "PARTIAL"
        assert not report.ok


class TestSkippedProvenanceReport:
    def test_skipped_reports_ok_but_is_not_a_verified_pass(self) -> None:
        report = skipped_provenance_report(
            "narrativetrace-pytest", "0.1.1", "not yet PRESENT at 0.1.1"
        )

        assert report.status == "SKIPPED"
        assert report.ok
        assert report.files == ()
