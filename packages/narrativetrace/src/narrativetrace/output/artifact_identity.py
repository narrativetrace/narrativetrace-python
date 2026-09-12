# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Which artifact one traced test invocation owns.

``ArtifactIdentity``. A test method used to be the whole answer to "which file does this trace go
in", which is wrong the moment the method runs more than once — a parameterized or repeated test.
Every invocation then wrote the same path and the last one won, so earlier evidence was
unreachable through the advertised files and one invocation's approved trace judged another's
structure. This is the identity every per-test artifact keys by: the trace, the JSON export, the
diagram, the structural artifact, and the committed approved trace beside them.

Cross-platform naming scheme, mirrored byte for byte from the reference format:

- An ordinary test method keeps its bare method slug — ``customerPlacesOrder`` →
  ``customer_places_order``. Nothing that exists today moves.
- An invocation appends ``-<index>-<label>``: the 1-based invocation index zero-padded to three
  digits, then the invocation's display name through the same slug rule, with runs of ``_``
  collapsed and the ends trimmed. The label is dropped when it slugs to nothing.
- ``-`` is the separator precisely because the slug alphabet is ``[a-z0-9_]`` and can never
  produce one: an ordinary method can never collide with an invocation artifact, and the name
  parses back into its three parts.
- Nothing here varies per process or per run: the index comes from the test runner's own
  invocation order and the label from the display name, so an approved trace recorded on one
  machine matches the artifact written on the next.

See :mod:`narrativetrace.output.paths` for the slug/truncation rules this delegates to.
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace.output.paths import file_slug
from narrativetrace.render.scenario import humanize

_BRACKET = "["


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    """One test invocation's identity: the test, and which run of it this is.

    Args:
        test_class_name: the test class, qualified or simple; never trusted to be either.
        method_name: the test method's own name, shared by every invocation of it.
        invocation_index: 1-based invocation number, or ``0`` for a method that runs once.
        invocation_label: the invocation's display name, ``""`` when there is none.
    """

    test_class_name: str
    method_name: str
    invocation_index: int = 0
    invocation_label: str = ""

    def __post_init__(self) -> None:
        if self.invocation_index < 0:
            raise ValueError("invocation_index must not be negative")

    @staticmethod
    def of_method(test_class_name: str, method_name: str) -> ArtifactIdentity:
        """The identity of a test method that runs exactly once — the artifact name it has
        always had."""
        return ArtifactIdentity(test_class_name, method_name)

    @staticmethod
    def of_invocation(
        test_class_name: str, method_name: str, invocation_index: int, invocation_label: str
    ) -> ArtifactIdentity:
        """The identity of one invocation of a test method that runs more than once.

        Args:
            invocation_index: 1-based, in the runner's invocation order.
            invocation_label: the invocation's display name, used only for readability.
        """
        if invocation_index < 1:
            raise ValueError(f"invocation_index is 1-based; got {invocation_index}")
        return ArtifactIdentity(test_class_name, method_name, invocation_index, invocation_label)

    @property
    def is_invocation(self) -> bool:
        """Whether this identity names one invocation of a repeated method rather than a whole
        method."""
        return self.invocation_index > 0

    def file_slug(self) -> str:
        """The artifact base name, without any format suffix: the scheme this class documents."""
        return file_slug(self.method_name, self.invocation_index, self.invocation_label)

    def _bare_method_name(self) -> str:
        """The method's own name, without a label a test runner appended to it — a runner that
        folds a parametrize label into the name itself (``equipment_can_be_found[KAYAK]``) never
        puts a bracket in a bare identifier, so everything from the first one belongs to the
        runner."""
        bracket = self.method_name.find(_BRACKET)
        return self.method_name if bracket < 0 else self.method_name[:bracket]

    def structural_scenario(self, display_name: str | None) -> str:
        """The scenario title the value-free artifacts carry — a title no runtime value can reach.

        The structural ``.nt`` artifact promises names, call hierarchy and outcome kinds and
        nothing else. A parametrized invocation's display name interpolates *arguments* into
        itself, so an invocation is titled by what the developer wrote (the method) and by which
        run it was (the index), never by what it ran with: ``<humanized method> #<index>``. A
        method that runs once keeps its display name, so every committed approved trace stays
        byte-identical — unless the caller has no display name of its own (it passed the method
        name itself), in which case a label a runner appended to that name is dropped the same
        way :meth:`_bare_method_name` drops it for an invocation.

        The *file* name is a separate question and deliberately keeps the label: it is what tells
        two invocations apart on disk (see this class's own naming rule).
        """
        if self.is_invocation:
            return f"{humanize(self._bare_method_name())} #{self.invocation_index}"
        if display_name is None or display_name == self.method_name:
            return humanize(self._bare_method_name())
        return humanize(display_name)
