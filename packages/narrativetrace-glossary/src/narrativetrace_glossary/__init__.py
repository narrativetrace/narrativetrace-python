# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Domain glossary for narrativetrace: ubiquitous language harvested from traces.

One checked-in ``glossary.json`` per repository is at once the translation dictionary, the
reviewable domain documentation, and the vocabulary norm clarity diagnostics enforce (ADR-012).
"""

from narrativetrace_glossary.alias_index import build_alias_index
from narrativetrace_glossary.clarity_issues import (
    NON_CANONICAL_TERM_CATEGORY,
    non_canonical_term_issues,
)
from narrativetrace_glossary.context_resolver import UNASSIGNED_CONTEXT, resolve_context
from narrativetrace_glossary.glossary_loader import load_glossary
from narrativetrace_glossary.harvester import HarvestCandidate, harvest_traces
from narrativetrace_glossary.json_reader import read_glossary_json
from narrativetrace_glossary.json_writer import write_glossary_json
from narrativetrace_glossary.markdown import render_glossary_markdown
from narrativetrace_glossary.merger import MergeResult, merge_harvest
from narrativetrace_glossary.models import (
    GLOSSARY_ABBREVIATIONS_SCHEMA_VERSION,
    GLOSSARY_SCHEMA_VERSION,
    BoundedContext,
    Glossary,
    GlossaryTerm,
    SynonymAlias,
    TermKey,
    TermKind,
    TermStatus,
)
from narrativetrace_glossary.normalizer import (
    TermCandidate,
    class_candidate,
    exception_candidate,
    method_candidates,
    normalize_phrase,
    parameter_candidate,
)
from narrativetrace_glossary.rename_suggester import suggest_rename
from narrativetrace_glossary.scaffolding import SUPPORTED_LOCALES, ScaffoldingBundle
from narrativetrace_glossary.summary_formatter import (
    format_violation_details,
    format_vocabulary_summary,
)
from narrativetrace_glossary.translation_file_sink import TranslationFileSink
from narrativetrace_glossary.translation_subscriber import (
    DEFAULT_CAPACITY,
    DEFAULT_TTL_SECONDS,
    TranslationSubscriber,
)
from narrativetrace_glossary.translation_view import RenderState, TraceTranslationView
from narrativetrace_glossary.translator import GlossaryTranslator, PhraseTranslation
from narrativetrace_glossary.usage_report import (
    USAGE_REPORT_FILE,
    usage_report_document,
    write_usage_report,
)
from narrativetrace_glossary.violations import VocabularyViolation, aggregate_violations
from narrativetrace_glossary.vocabulary import (
    GLOSSARY_FILE,
    glossary_vocabulary,
    read_project_vocabulary,
)

__all__ = [
    "DEFAULT_CAPACITY",
    "DEFAULT_TTL_SECONDS",
    "GLOSSARY_ABBREVIATIONS_SCHEMA_VERSION",
    "GLOSSARY_FILE",
    "GLOSSARY_SCHEMA_VERSION",
    "NON_CANONICAL_TERM_CATEGORY",
    "SUPPORTED_LOCALES",
    "UNASSIGNED_CONTEXT",
    "USAGE_REPORT_FILE",
    "BoundedContext",
    "Glossary",
    "GlossaryTerm",
    "GlossaryTranslator",
    "HarvestCandidate",
    "MergeResult",
    "PhraseTranslation",
    "RenderState",
    "ScaffoldingBundle",
    "SynonymAlias",
    "TermCandidate",
    "TermKey",
    "TermKind",
    "TermStatus",
    "TraceTranslationView",
    "TranslationFileSink",
    "TranslationSubscriber",
    "VocabularyViolation",
    "aggregate_violations",
    "build_alias_index",
    "class_candidate",
    "exception_candidate",
    "format_violation_details",
    "format_vocabulary_summary",
    "glossary_vocabulary",
    "harvest_traces",
    "load_glossary",
    "merge_harvest",
    "method_candidates",
    "non_canonical_term_issues",
    "normalize_phrase",
    "parameter_candidate",
    "read_glossary_json",
    "read_project_vocabulary",
    "render_glossary_markdown",
    "resolve_context",
    "suggest_rename",
    "usage_report_document",
    "write_glossary_json",
    "write_usage_report",
]
