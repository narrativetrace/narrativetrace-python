# Canonical JSON schemas

The cross-platform output contract. Every NarrativeTrace runtime keeps a **byte-identical**
mirror; the master copy lives at `narrativetrace-core/src/test/resources/schema/`. Regenerate by
copying again; never hand-edit here — a runtime that edits the contract has left the contract.

| File | Validates |
|---|---|
| `entry.schema.json` | one flat canonical event — the `.canonical.json` artifact is an array of these |
| `chapter.schema.json` | one service's whole contribution (`export_chapter`) |
| `chapter-tree.schema.json` | the nested tree embedded in `nt.chapterTree`, and the per-test `.json` companion |

These are **test resources**, not shipped in any distribution: they exist so schema drift fails a
build instead of being discovered by a consumer. `packages/narrativetrace/tests/schemas.py` loads
them and `validate_against` raises on the first violation.

Licence: the schemas are Apache 2.0, unlike the BSL-1.1 runtime — the output format is an open
standard (see the root `README.md`). They carry no SPDX header, so the publish-time licence gate
does not see them.
