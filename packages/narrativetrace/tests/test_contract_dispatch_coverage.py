# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The guard that should have caught `config-shape-logger-threshold-does-not-shrink-capture`:
the entry was added to `documentation/contract.yaml` with its probe module already written, but
never wired into `contract_probe.runner._DISPATCH`. The nightly contract gate did not report it
as a failing row -- it crashed with a `RuntimeError` partway through the run, a far worse signal
than a FAILS line, and one no amount of rerunning would explain.

Mirrors Java's `ContractDispatchCoverageTest` (`contract-probe/src/test/java/ai/narrativetrace/
contract/ContractDispatchCoverageTest.java`): derived from the contract file itself, not a list
of ids kept here, so an entry added tomorrow is covered the moment it lands.

A near-identical assertion already lives in `contract-probe/tests/test_runner.py` (added
2026-09-18 for the previous instance of this same gap, `probed-run-name-console-footer` /
`probed-run-name-manifest-field`) but that guard never actually runs: `contract-probe/` is a
deliberately standalone `uv` project, not a member of this workspace and not covered by this
repository's `testpaths` (`packages`, `examples`), and no CI workflow invokes its test suite
either -- so the assertion existed but nothing executed it, and it could not have caught today's
gap any more than it caught the fact that it itself was silent. This copy runs where `poe test`/
`poe check` actually look: inside a `packages/*` test suite, every commit, no network -- narrative
Trace is already installed here as the very package under test, so importing every probe module
(each one imports only `narrativetrace`, never a sibling PyPI package) needs no registry call.
"""

from __future__ import annotations

import sys

from scripts.translation_check import REPO_ROOT

_CONTRACT_PROBE_SRC = REPO_ROOT / "contract-probe" / "src"
if str(_CONTRACT_PROBE_SRC) not in sys.path:
    sys.path.insert(0, str(_CONTRACT_PROBE_SRC))

from contract_probe import runner  # noqa: E402 -- sys.path must be extended first
from contract_probe.contract_yaml import read  # noqa: E402

_CONTRACT_PATH = REPO_ROOT / "documentation" / "contract.yaml"


def _dispatchable_ids() -> set[str]:
    return set(runner._ENTRY_POINT_IDS) | set(runner._DISPATCH)


def test_every_contract_entry_has_a_probe_dispatch() -> None:
    """Every `documentation/contract.yaml` entry must resolve through `runner._observe` --
    either the entry-point probe (`_ENTRY_POINT_IDS`) or a registered `_DISPATCH` callable -- or
    the nightly gate crashes on it instead of reporting a verdict."""
    entries = read(_CONTRACT_PATH)
    assert entries, f"read no entries from {_CONTRACT_PATH}"

    undispatched = [entry.id for entry in entries if entry.id not in _dispatchable_ids()]

    assert undispatched == [], (
        "contract.yaml entries with no probe dispatch -- add each in runner._DISPATCH "
        "(or runner._ENTRY_POINT_IDS), or the nightly gate crashes on it instead of reporting a "
        f"verdict: {undispatched}"
    )


def test_every_probe_dispatch_answers_a_contract_entry() -> None:
    """The other direction: a dispatch for an id the contract no longer carries is dead code that
    silently never runs, and the pair of assertions is what makes the two lists one list."""
    ids = {entry.id for entry in read(_CONTRACT_PATH)}

    orphaned = sorted(dispatched for dispatched in runner._DISPATCH if dispatched not in ids)

    assert orphaned == [], f"probe dispatches for ids no longer in contract.yaml: {orphaned}"
