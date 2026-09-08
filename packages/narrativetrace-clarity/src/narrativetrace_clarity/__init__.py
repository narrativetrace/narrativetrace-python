# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Naming-clarity analysis for narrativetrace traces (dictionaries + scorers + CLI gate).

The clarity engine, with dictionaries byte-identical across runtimes: 828 domain / 1053 total
verbs, 187 abbreviations, 35 collocation maps, role suffixes, and the five weighted scorers. The
:func:`~narrativetrace_clarity.analyzer.analyze` engine scores any core ``TraceTree``; the
``narrativetrace-clarity`` console script scans Python sources and gates the build.
"""

from narrativetrace_clarity.analyzer import analyze
from narrativetrace_clarity.json_export import export
from narrativetrace_clarity.models import ClarityIssue, ClarityResult, Severity
from narrativetrace_clarity.report import render, render_suite_report
from narrativetrace_clarity.vocabulary import EMPTY, DomainVocabulary

__version__ = "0.1.0"

__all__ = [
    "EMPTY",
    "ClarityIssue",
    "ClarityResult",
    "DomainVocabulary",
    "Severity",
    "analyze",
    "export",
    "render",
    "render_suite_report",
]
