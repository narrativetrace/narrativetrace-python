# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Console reporting, template-warning detection, and trace file writing helpers."""

from narrativetrace.output.artifact_identity import ArtifactIdentity
from narrativetrace.output.paths import (
    diagram_file,
    extension_for_format,
    file_slug,
    trace_directory,
    trace_file,
)
from narrativetrace.output.reporter import ConsoleSummaryReporter
from narrativetrace.output.warnings import TemplateWarning, collect, format_warnings
from narrativetrace.output.writer import TraceArtifact, WriteResult, write_trace

__all__ = [
    "ArtifactIdentity",
    "ConsoleSummaryReporter",
    "TemplateWarning",
    "TraceArtifact",
    "WriteResult",
    "collect",
    "diagram_file",
    "extension_for_format",
    "file_slug",
    "format_warnings",
    "trace_directory",
    "trace_file",
    "write_trace",
]
