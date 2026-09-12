# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The narrativetrace pytest plugin: fixture, per-test artifacts, and suite reporting.

The JUnit4/5 extension behaviours (testfx-logging-otel §TS-TESTFX-*). The ``narrative_trace``
fixture builds a fresh context at the env-configured level; on teardown it emits template warnings,
prints a framed execution trace for failed tests, and (when output is enabled) writes per-test
artifacts. A session reporter prints the suite header/footer.

Artifacts match the Java JUnit integration so conformance fixtures can compare them across
platforms: the ``.json`` companion is the full ``export_document`` envelope (``version`` +
``scenario``), and the scenario result travels as a
:class:`~narrativetrace.render.scenario_result.ScenarioResult` — ``success``/``error`` in the JSON
artifact, ``PASSED``/``FAILED`` in the Markdown caption.

Environment channels: ``NARRATIVETRACE_LEVEL`` (garbage → DETAIL), ``NARRATIVETRACE_OUTPUT``
(on by default; ``false``/``0``/``no``/``off``, case-insensitively, opt out — anything else
truthy), ``NARRATIVETRACE_OUTPUT_DIR`` (default ``narrative-traces``),
``NARRATIVETRACE_FORMAT`` (default ``markdown``; ``text``/``mermaid``/``plantuml`` replace the
Markdown trace, and only ``markdown`` carries the ``.json`` + ``.mmd`` companions),
``NARRATIVETRACE_CANONICAL`` (truthy → also write the per-test ``.canonical.json`` entry array,
whatever the format; off by default because it is a machine artifact for conformance runners).

Structural artifact + approval mode (the markdown path only): each non-empty test additionally
writes a value-free ``.nt`` structural artifact beside its narrative -- names, call shape and
outcome kinds only, no runtime values (see :mod:`narrativetrace.render.structural`). The file on
disk is the last-green baseline: it advances only when the run's overall verdict is green
(assertions passed *and*, when approval mode is on, structure approved), and a non-green run's
delta against it is reported on the suite footer's ``Since last green:`` line and, for the failing
test itself, in place of the full execution trace when the structure changed.
``NARRATIVETRACE_APPROVAL`` (default off) turns on approval mode: a passing test's structure is
verified against a committed approved trace under ``NARRATIVETRACE_APPROVED_DIR`` (default
``test-narratives``), failing the test with a readable diff on any mismatch — see
:mod:`narrativetrace.output.approval` and the ``narrativetrace-approve`` console script / ``poe
approve`` task.

A parameterized invocation (any item pytest built from a ``callspec``) gets its own per-invocation
artifacts, keyed by :class:`~narrativetrace.output.artifact_identity.ArtifactIdentity`: the run
also writes ``manifest.json`` (one row per traced scenario, naming its test, invocation number, and
every file it owns), and the invocation's structural header is titled by the method and its
1-based invocation index (``Equipment can be found #2``), never by the display name a
``parametrize`` id may have interpolated arguments into.

Clarity aggregation (PY12): each test's captured tree is scored, the suite footer prints a
high/moderate/low split, and (when output is enabled) a ``clarity-results.json`` plus Markdown
suite report are written with one entry per test (duplicate scenario names retained).

Loss reporting: each test's :meth:`~narrativetrace.context.NarrativeContext.trace_loss` reading is
summed (one context per test, so readings add rather than needing a difference), and the footer
names what the suite lost on one line — omitted entirely when it lost nothing.

Glossary harvest hook (Phase 5): opt-in by ``glossary.json`` presence — a suite harvests only when
the repository has already committed a glossary, unless ``NARRATIVETRACE_GLOSSARY`` overrides that
default (``off`` disables unconditionally; any other truthy value forces harvesting even with no
glossary.json yet, which then creates one). Distinct from ``NARRATIVETRACE_GLOSSARY_DIR``, which
names *where* the glossary lives for both this hook and the unconditional vocabulary read above;
harvesting itself always writes the merged glossary/usage report back once it runs, independent of
``NARRATIVETRACE_OUTPUT`` (that key gates trace-file artifacts, an unrelated concern).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from narrativetrace_clarity import analyze as analyze_clarity
from narrativetrace_clarity import export as export_clarity
from narrativetrace_clarity import render_suite_report
from narrativetrace_clarity.models import ClarityResult
from narrativetrace_clarity.vocabulary import EMPTY, DomainVocabulary
from narrativetrace_diagrams.mermaid import MermaidSequenceDiagramRenderer
from narrativetrace_diagrams.plantuml import PlantUmlSequenceDiagramRenderer
from narrativetrace_glossary.class_package_index import class_package_index
from narrativetrace_glossary.harvester import harvest_traces
from narrativetrace_glossary.json_reader import read_glossary_json
from narrativetrace_glossary.models import Glossary
from narrativetrace_glossary.suite_harvest import GLOSSARY_JSON_FILE, run_suite_harvest
from narrativetrace_glossary.summary_formatter import format_violation_details
from narrativetrace_glossary.vocabulary import read_project_vocabulary

from narrativetrace.config import ConfigResolver
from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.export import export_document as export_document_json
from narrativetrace.levels import NarrativeTraceConfig
from narrativetrace.loss import TraceLoss
from narrativetrace.output import approval as approval_mode
from narrativetrace.output import manifest as scenario_manifest
from narrativetrace.output.artifact_identity import ArtifactIdentity
from narrativetrace.output.reporter import ConsoleSummaryReporter
from narrativetrace.output.structural_delta import ScenarioDelta
from narrativetrace.output.warnings import collect, format_warnings
from narrativetrace.output.writer import TraceArtifact, WriteResult, write_trace
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.indented import IndentedTextRenderer
from narrativetrace.render.scenario import humanize
from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.tree import TraceTree

_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(slots=True)
class _OutputSettings:
    enabled: bool
    base_dir: Path
    fmt: str
    canonical: bool = False
    approval: bool = False
    approved_dir: Path = field(default_factory=lambda: Path("test-narratives"))


def _truthy(resolver: ConfigResolver, key: str, default: str = "") -> bool:
    return (resolver.resolve(key, default) or "").strip().lower() in _TRUTHY


def _output_settings(resolver: ConfigResolver) -> _OutputSettings:
    """Reads the output keys through the shared precedence chain (env → config file → default).

    ``output`` defaults to on: an adopter who wraps a call with the fixture gets trace artifacts
    without also having to discover and set an enable flag. ``NARRATIVETRACE_OUTPUT=false`` (also
    ``0``/``no``/``off``, case-insensitively — anything outside ``_TRUTHY`` opts out) or
    ``output = false`` in a config file turns it back off.

    ``approval`` (default off) turns on approval mode against the committed traces under
    ``approved_dir`` (default ``test-narratives``) — see :mod:`narrativetrace.output.approval`.
    """
    enabled = _truthy(resolver, "output", "true")
    base_dir = Path((resolver.resolve("output_dir", "") or "").strip() or "narrative-traces")
    fmt = (resolver.resolve("format", "") or "").strip() or "markdown"
    approved_dir = Path((resolver.resolve("approved_dir", "") or "").strip() or "test-narratives")
    return _OutputSettings(
        enabled,
        base_dir,
        fmt,
        _truthy(resolver, "canonical"),
        _truthy(resolver, "approval"),
        approved_dir,
    )


def _resolver(config: pytest.Config) -> ConfigResolver:
    """One resolver per session — file discovery walks the filesystem and must not run per test."""
    existing = getattr(config, "_narrativetrace_resolver", None)
    if existing is None:
        existing = ConfigResolver()
        config._narrativetrace_resolver = existing  # type: ignore[attr-defined]
    return existing


@dataclass(slots=True)
class _SuiteAccumulator:
    scenarios: list[str] = field(default_factory=list)
    clarity: list[tuple[str, ClarityResult]] = field(default_factory=list)
    loss: TraceLoss = field(default_factory=TraceLoss.none)
    harvest_trees: list[TraceTree] = field(default_factory=list)
    deltas: list[ScenarioDelta] = field(default_factory=list)
    manifest_entries: list[scenario_manifest.Entry] = field(default_factory=list)
    invocation_counts: dict[tuple[str, str], int] = field(default_factory=dict)


def _glossary_dir(config: pytest.Config) -> str:
    return (_resolver(config).resolve("glossary_dir", "") or "").strip() or "."


def _harvest_enabled(config: pytest.Config) -> bool:
    """Opt-in by ``glossary.json`` presence, with an explicit ``NARRATIVETRACE_GLOSSARY`` override.

    ``off`` disables harvesting unconditionally, even with a glossary already committed — the
    mid-suite equivalent of Java's suite extension defaulting to ``disabled()``. Any other truthy
    value forces harvesting on, even with no ``glossary.json`` yet (a project's first opt-in run,
    which then creates one). Unset defaults to "harvest only when a glossary.json already exists"
    — the least-surprising default: a project that has never curated a glossary does not get one
    silently written just by running its test suite.
    """
    override = (_resolver(config).resolve("glossary", "") or "").strip().lower()
    if override == "off":
        return False
    if override in _TRUTHY:
        return True
    return (Path(_glossary_dir(config)) / GLOSSARY_JSON_FILE).is_file()


def _project_vocabulary(config: pytest.Config) -> DomainVocabulary:
    """The repository's committed glossary, read once per session as the scoring vocabulary.

    Unlike harvesting, reading is unconditional: it changes nothing on disk, and a project that
    curates its ubiquitous language should not have to opt in to being scored in it. Only the
    committed file counts — nothing this run harvests feeds back into its own scores.

    ``narrativetrace.glossary_dir`` (env ``NARRATIVETRACE_GLOSSARY_DIR``) names the directory,
    defaulting to the working directory. A glossary that cannot be read degrades to the built-in
    dictionaries with a warning: a reporting artifact must never fail the suite that produced it.
    """
    existing = getattr(config, "_narrativetrace_vocabulary", None)
    if existing is not None:
        return cast("DomainVocabulary", existing)
    glossary_dir = _glossary_dir(config)
    try:
        resolved = read_project_vocabulary(glossary_dir)
    except (OSError, ValueError) as error:
        print(
            f"narrative-trace: committed glossary at {glossary_dir} could not be read, "
            f"scoring with the built-in dictionaries only ({error})"
        )
        resolved = EMPTY
    config._narrativetrace_vocabulary = resolved  # type: ignore[attr-defined]
    return resolved


def _accumulator(config: pytest.Config) -> _SuiteAccumulator:
    existing = getattr(config, "_narrativetrace_acc", None)
    if existing is None:
        existing = _SuiteAccumulator()
        config._narrativetrace_acc = existing  # type: ignore[attr-defined]
    return existing


def _class_name(request: pytest.FixtureRequest) -> str:
    node_cls = getattr(request.node, "cls", None)
    if node_cls is not None:
        return str(node_cls.__name__)
    return str(request.module.__name__).rsplit(".", 1)[-1]


def _artifact_identity(request: pytest.FixtureRequest) -> ArtifactIdentity:
    """One test invocation's identity (see
    :class:`~narrativetrace.output.artifact_identity.ArtifactIdentity`).

    An ordinary test keeps its bare method slug. Any item pytest built from a ``callspec`` --
    every ``@pytest.mark.parametrize``/parametrized-fixture invocation, regardless of how many
    total cases exist -- is an invocation instead: its 1-based index is this run's own execution
    order for that (class, method) pair (a session-scoped counter, the pytest analogue of the
    reference runtime's test-template invocation number), and its label is pytest's own
    parametrize id -- the readable part of the file name, never the part two invocations are told
    apart by. ``node.originalname`` is pytest's own pre-parametrize function name, so it already
    carries no bracket suffix to strip (unlike a JUnit 4 style runner that folds a label into the
    method name itself).
    """
    class_name = _class_name(request)
    node = request.node
    callspec = getattr(node, "callspec", None)
    if callspec is None:
        return ArtifactIdentity.of_method(class_name, node.name)
    bare_name = str(getattr(node, "originalname", None) or node.name)
    counts = _accumulator(request.config).invocation_counts
    key = (class_name, bare_name)
    counts[key] = counts.get(key, 0) + 1
    return ArtifactIdentity.of_invocation(class_name, bare_name, counts[key], str(callspec.id))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Iterator[None]:
    outcome = yield
    report = outcome.get_result()  # type: ignore[attr-defined]
    setattr(item, f"_nt_rep_{report.when}", report)


@pytest.fixture
def narrative_trace(request: pytest.FixtureRequest) -> Iterator[ContextVarNarrativeContext]:
    """A fresh capture context at the env-configured level; writes artifacts on teardown."""
    context = ContextVarNarrativeContext(
        NarrativeTraceConfig.resolve(resolver=_resolver(request.config))
    )
    yield context
    _finish(context, request)


def _finish(context: ContextVarNarrativeContext, request: pytest.FixtureRequest) -> None:
    """Teardown: aggregate for the suite, verify approval, write per-test artifacts, report.

    Sequencing matters (mirrors the reference runtime's exact fix for the same race): the
    approval verdict is settled *before* anything is written, and a rejection is folded into the
    write's own verdict -- so a rejected structure can never advance the last-green baseline, and
    the test still fails with the original approval-mismatch message once every artifact a
    reviewer needs is already on disk.
    """
    tree = context.capture_trace()
    scenario = humanize(request.node.name)
    loss = context.trace_loss()
    _accumulate(request.config, scenario, tree, loss)

    warning_text = format_warnings(collect(tree))
    if warning_text:
        print(warning_text)

    report = getattr(request.node, "_nt_rep_call", None)
    test_failed = report is not None and report.failed
    identity = _artifact_identity(request)
    settings = _output_settings(_resolver(request.config))

    rejection = _approval_rejection(tree, identity, request, settings, loss, test_failed)
    combined_failed = test_failed or rejection is not None

    write_result = _write_artifacts(
        tree, scenario, identity, request, settings, failed=combined_failed
    )
    _accumulate_write_result(request.config, scenario, identity, settings, write_result)
    _report_result(tree, scenario, write_result, failed=combined_failed)

    if rejection is not None:
        raise rejection


def _report_result(
    tree: TraceTree, scenario: str, write_result: WriteResult | None, *, failed: bool
) -> None:
    """Prints this invocation's console output: the delta-aware failure report when the run is
    not green, else the plain write echo -- never both, so a failure is never double-printed."""
    if write_result is None:
        return
    if failed:
        trace_text = IndentedTextRenderer().render(tree)
        report = ConsoleSummaryReporter().format_failure_report(
            scenario, trace_text, write_result.delta
        )
        print(report)
    elif write_result.files:
        print(write_result.console_echo)


def _approval_rejection(
    tree: TraceTree,
    identity: ArtifactIdentity,
    request: pytest.FixtureRequest,
    settings: _OutputSettings,
    loss: TraceLoss,
    test_failed: bool,
) -> AssertionError | None:
    """Verifies the scenario against its committed approved trace when approval mode is on.

    Never runs for a test that already failed on its own (Java: "failed ? Optional.empty() :
    approvalRejection(...)") -- approval only judges a test that would otherwise have passed.
    """
    if test_failed or not settings.approval or tree.is_empty:
        return None
    scenario_title = identity.structural_scenario(request.node.name)
    approved_path = approval_mode.approved_file(settings.approved_dir, identity)
    try:
        note = approval_mode.verify(tree, scenario_title, approved_path, loss)
    except AssertionError as rejection:
        return rejection
    if note:
        print(f"  Approval: {note}")
    return None


def _accumulate_write_result(
    config: pytest.Config,
    scenario: str,
    identity: ArtifactIdentity,
    settings: _OutputSettings,
    write_result: WriteResult | None,
) -> None:
    """Records this invocation's structural delta and manifest row, when anything was written."""
    if write_result is None:
        return
    accumulator = _accumulator(config)
    if write_result.delta is not None:
        accumulator.deltas.append(write_result.delta)
    if write_result.files:
        accumulator.manifest_entries.append(
            scenario_manifest.entry_for(settings.base_dir, identity, scenario)
        )


def _accumulate(config: pytest.Config, scenario: str, tree: TraceTree, loss: TraceLoss) -> None:
    """Records the scenario for the footer, scoring clarity for non-empty traces.

    Each test gets its own context, so per-test readings sum: nothing is double-counted the way
    a difference against a process-wide counter would be.
    """
    accumulator = _accumulator(config)
    accumulator.scenarios.append(scenario)
    accumulator.loss = accumulator.loss.plus(loss)
    if not tree.is_empty:  # clarity aggregates non-empty traces (Java's GlobalTraceAccumulator)
        accumulator.clarity.append((scenario, analyze_clarity(tree, _project_vocabulary(config))))
        if _harvest_enabled(config):
            accumulator.harvest_trees.append(tree)


def _write_artifacts(
    tree: TraceTree,
    scenario: str,
    identity: ArtifactIdentity,
    request: pytest.FixtureRequest,
    settings: _OutputSettings,
    *,
    failed: bool,
) -> WriteResult | None:
    """Writes this test's trace artifacts when output is enabled and anything was captured.

    Returns ``None`` precisely when nothing was written (output disabled, or an empty trace) --
    the caller's cue to skip both console output and suite accumulation for this invocation.
    """
    if not settings.enabled or tree.is_empty:
        return None
    metadata = TraceMetadata(scenario, ScenarioResult.of(failed))
    return write_trace(
        tree,
        metadata,
        TraceArtifact(
            settings.base_dir,
            identity.test_class_name,
            identity.method_name,
            settings.fmt,
            canonical=settings.canonical,
            identity=identity,
            display_name=request.node.name,
        ),
        json_exporter=lambda captured: export_document_json(captured, metadata),
        diagram_renderer=MermaidSequenceDiagramRenderer().render,
        plantuml_renderer=PlantUmlSequenceDiagramRenderer().render,
    )


def pytest_terminal_summary(terminalreporter: Any) -> None:
    """Prints the suite footer with the clarity split; writes clarity artifacts if enabled."""
    accumulator = getattr(terminalreporter.config, "_narrativetrace_acc", None)
    if accumulator is None or not accumulator.scenarios:
        return
    reporter = ConsoleSummaryReporter()
    settings = _output_settings(_resolver(terminalreporter.config))
    scores = [result.overall_score for _, result in accumulator.clarity]
    terminalreporter.write_line(
        reporter.format_suite_footer(
            len(accumulator.scenarios), str(settings.base_dir), scores, accumulator.loss
        )
    )
    delta_line = reporter.format_delta_line(accumulator.deltas)
    if delta_line:
        terminalreporter.write_line(f"  Since last green: {delta_line}")
    if settings.enabled and accumulator.clarity:
        _write_clarity_reports(accumulator.clarity, settings.base_dir)
    if settings.enabled and accumulator.manifest_entries:
        scenario_manifest.write(accumulator.manifest_entries, settings.base_dir)
    if accumulator.harvest_trees:
        _run_harvest(
            terminalreporter.config, accumulator.harvest_trees, settings.base_dir, terminalreporter
        )


def _write_clarity_reports(clarity: list[tuple[str, ClarityResult]], base_dir: Path) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "clarity-results.json").write_text(export_clarity(clarity), encoding="utf-8")
    (base_dir / "clarity-report.md").write_text(render_suite_report(clarity), encoding="utf-8")


def _context_glossary(glossary_dir: str) -> Glossary:
    """Reads the committed glossary for bounded-context resolution only.

    Separate from :func:`~narrativetrace_glossary.suite_harvest.run_suite_harvest`'s own read of
    the same file (for the merge) — a malformed file must not break context resolution silently,
    so this degrades to an empty glossary (every candidate files under ``_unassigned``) rather than
    raising into a terminal-summary hook that must never crash the suite that already passed.
    """
    path = Path(glossary_dir) / GLOSSARY_JSON_FILE
    if not path.is_file():
        return Glossary()
    try:
        return read_glossary_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Glossary()


def _run_harvest(
    config: pytest.Config, trees: list[TraceTree], base_dir: Path, terminalreporter: Any
) -> None:
    """Harvests, merges, writes back, and reports — the opt-in half of glossary maintenance.

    A failure here (a malformed committed glossary, an unwritable directory) is reported and
    swallowed: harvesting is a maintenance side effect of running the suite, never a reason the
    suite itself should be reported as broken.
    """
    glossary_dir = _glossary_dir(config)
    try:
        module_of = class_package_index(trees)
        candidates = harvest_traces(
            trees, glossary=_context_glossary(glossary_dir), module_of=module_of
        )
        result = run_suite_harvest(candidates, glossary_dir=glossary_dir, output_dir=str(base_dir))
    except (OSError, ValueError) as error:
        terminalreporter.write_line(f"narrative-trace: glossary harvest failed, skipped ({error})")
        return
    terminalreporter.write_line(result.summary)
    details = format_violation_details(result.violations)
    if details:
        terminalreporter.write_line(details)
