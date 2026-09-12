# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Docs-as-tests gate (`poe snippet-check`, wired into `poe check`; `poe snippet-sync` writes).

Rule 8 (docs as tests, family-wide): a quickstart's code
and output are embedded from a project the build compiles, tests and runs, never typed into the
page. This module is the mechanism, the same one `scripts/translation_check.py` already runs for
translated code-block content — pointed at the source instead of another language's copy.

An English documentation page opts a fenced code block in by wrapping it with an HTML-comment
marker pair, invisible on GitHub and in the site's doc viewer::

    <!-- snippet: examples/sixty_seconds/main.py -->
    ```python
    …the file, verbatim…
    ```
    <!-- /snippet -->

`snippet:` names a path relative to the repository root, followed by space-separated
`key=value` options:

- `region=NAME` — the fenced content is not the whole file but the window between a
  `# snippet:begin NAME` / `# snippet:end NAME` comment pair inside it (either line's leading `#`
  may also be `//`, for a future non-Python source) — so imports or test scaffolding can be hidden
  from the page without duplicating the file.
- `diff=PATH` — the fenced content is the unified diff from the marker's own path (the "before")
  to `PATH` (the "after"), header-less (no `---`/`+++`/`@@` lines) — the shape a `diff`-fenced
  block showing what a change does to a file already has.
- `mask=duration` (the only mask, for now) — before comparing, both the page's block and the
  freshly rendered source have `— \\d+(\\.\\d+)?ms` replaced with `— Nms`, so a real run's timing
  never fails the build; the page keeps its own "timing varies" sentence and `sync` still writes
  the *real* measured duration to the page, only the comparison is masked.

`check_repository` reports every block whose page content no longer matches what its source
renders (masked); `sync_repository` rewrites each drifted block in place — English pages only, the
same split `translation_check.py` already draws between staleness (checked) and translated content
(never auto-rewritten). A missing/malformed marker pair is an authoring bug, not a degrade case, so
parsing raises rather than skipping silently — the same choice `translation_check`'s manifest
parsing makes for the same reason.
"""

from __future__ import annotations

import difflib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.llms_banner import check_banner
from scripts.translation_check import REPO_ROOT, translated_files

_MARKER_OPEN_RE = re.compile(r"^<!--\s*snippet:\s*(?P<rest>.+?)\s*-->\s*$")
_MARKER_CLOSE = "<!-- /snippet -->"
_FENCE_OPEN_RE = re.compile(r"^```(\S*)\s*$")
_FENCE_CLOSE = "```"
_DURATION_RE = re.compile(r"— \d+(\.\d+)?ms")
_REGION_BEGIN_TEMPLATE = r"^\s*(?:#|//)\s*snippet:begin\s+{name}\s*$"
_REGION_END_TEMPLATE = r"^\s*(?:#|//)\s*snippet:end\s+{name}\s*$"
_LICENSE_HEADER_MARKERS = (
    "SPDX-License-Identifier",
    "Licensed under",
    "Change License",
    "Copyright (c)",
)


@dataclass(frozen=True, slots=True)
class SnippetSpan:
    """One `<!-- snippet: ... --> ... <!-- /snippet -->` block, as line indices into a page."""

    open_line: int
    content_start: int
    content_end: int  # exclusive — index of the closing ``` fence line
    close_line: int
    source_path: str
    options: dict[str, str] = field(default_factory=dict)


def _parse_marker_rest(rest: str) -> tuple[str, dict[str, str]]:
    tokens = rest.split()
    options = dict(token.split("=", 1) for token in tokens[1:])
    return tokens[0], options


def parse_spans(text: str) -> list[SnippetSpan]:
    """Every snippet block in `text`, in document order. Raises on a malformed marker pair."""
    lines = text.split("\n")
    spans = []
    line = 0
    while line < len(lines):
        marker = _MARKER_OPEN_RE.match(lines[line])
        if marker is None:
            line += 1
            continue
        source_path, options = _parse_marker_rest(marker.group("rest"))
        spans.append(_parse_one_span(lines, line, source_path, options))
        line = spans[-1].close_line + 1
    return spans


def _parse_one_span(
    lines: list[str], open_line: int, source_path: str, options: dict[str, str]
) -> SnippetSpan:
    fence_line = open_line + 1
    if fence_line >= len(lines) or _FENCE_OPEN_RE.match(lines[fence_line]) is None:
        raise ValueError(f"line {open_line + 1}: 'snippet:' marker is not followed by a fence")
    content_start = fence_line + 1
    content_end = content_start
    while content_end < len(lines) and lines[content_end].rstrip() != _FENCE_CLOSE:
        content_end += 1
    if content_end >= len(lines):
        raise ValueError(f"line {open_line + 1}: snippet's fenced code block never closes")
    close_line = content_end + 1
    if close_line >= len(lines) or lines[close_line].strip() != _MARKER_CLOSE:
        raise ValueError(f"line {open_line + 1}: snippet marker has no matching '/snippet'")
    return SnippetSpan(open_line, content_start, content_end, close_line, source_path, options)


def _region_content(source_text: str, region: str) -> str:
    begin_re = re.compile(_REGION_BEGIN_TEMPLATE.format(name=re.escape(region)))
    end_re = re.compile(_REGION_END_TEMPLATE.format(name=re.escape(region)))
    lines = source_text.split("\n")
    start = next((i for i, source_line in enumerate(lines) if begin_re.match(source_line)), None)
    if start is None:
        raise ValueError(f"region '{region}': no 'snippet:begin {region}' marker in the source")
    end = next(
        (i for i in range(start + 1, len(lines)) if end_re.match(lines[i])),
        None,
    )
    if end is None:
        raise ValueError(f"region '{region}': no matching 'snippet:end {region}' marker")
    return "\n".join(lines[start + 1 : end])


def _strip_license_header(text: str) -> str:
    """Strips a publish-time-stamped license header from snippeted SOURCE content, never from
    the page side (the page never shows one). The (private) publish pipeline prepends a run of
    `#` comment lines (an SPDX identifier, a license grant) plus one blank line ahead of every
    tracked file's real content in the public snapshot -- see
    `scripts/check_no_license_headers.py`'s own docstring. Left unstripped, every snippeted
    source would drift the instant it is published, since the page's fenced block only ever
    shows the file as it reads in this private tree.

    Only a leading run of `#` lines whose *joined* text names an SPDX identifier or a license
    grant counts as this header -- any other leading comment (a tutorial's own `# main.py` first
    line, for instance) is left exactly as it is, blank line and all.
    """
    lines = text.split("\n")
    # The stamp is a run of `#` lines with NO blank line after it, so the file's own first
    # comment (`# main.py`) touches it directly: the header ends at its LAST marker line, never
    # at the first non-`#` line, or that label would be swallowed with it.
    end = 0
    while end < len(lines) and lines[end].startswith("#"):
        end += 1
    last_marker = -1
    for i in range(end):
        if any(marker in lines[i] for marker in _LICENSE_HEADER_MARKERS):
            last_marker = i
    if last_marker < 0:
        return text
    end = last_marker + 1
    if end < len(lines) and lines[end] == "":
        end += 1
    return "\n".join(lines[end:])


def _read_source(repo_root: Path, path: str) -> str:
    """A snippet source file's content, with any stamped license header stripped."""
    return _strip_license_header((repo_root / path).read_text(encoding="utf-8"))


def _diff_content(repo_root: Path, old_path: str, new_path: str) -> str:
    """The `diff`-fenced content for `old_path` → `new_path`: header-less unified diff."""
    old_lines = _read_source(repo_root, old_path).splitlines(keepends=True)
    new_lines = _read_source(repo_root, new_path).splitlines(keepends=True)
    context = max(len(old_lines), len(new_lines))
    diff_lines = list(difflib.unified_diff(old_lines, new_lines, n=context))
    body = diff_lines[3:]  # drop the `---`/`+++`/`@@` header lines: no file names, one hunk
    return "".join(body).rstrip("\n")


def expected_content(repo_root: Path, span: SnippetSpan) -> str:
    """What `span`'s fenced block should read, straight from its declared source (unmasked)."""
    if "diff" in span.options:
        return _diff_content(repo_root, span.source_path, span.options["diff"])
    source_text = _read_source(repo_root, span.source_path)
    if "region" in span.options:
        return _region_content(source_text, span.options["region"])
    return source_text.rstrip("\n")


def _masked(text: str, options: dict[str, str]) -> str:
    if options.get("mask") == "duration":
        return _DURATION_RE.sub("— Nms", text)
    return text


def _actual_content(lines: list[str], span: SnippetSpan) -> str:
    return "\n".join(lines[span.content_start : span.content_end])


def _source_label(span: SnippetSpan) -> str:
    if "diff" in span.options:
        return f"{span.source_path} diff={span.options['diff']}"
    if "region" in span.options:
        return f"{span.source_path} region={span.options['region']}"
    return span.source_path


def _english_markdown_files(repo_root: Path) -> list[Path]:
    """Every `documentation/**/*.md` file that is a source, not a translation (mirrors excluded
    the same way `scripts/translation_check.py` tells the two apart), plus `documentation/llms.txt`
    -- the one non-`.md` page an agent reads first, English-only and outside the translation
    manifest, whose embedded blocks must be just as drift-proof as any guide's."""
    translated = {path.resolve() for path in translated_files(repo_root)}
    documentation = repo_root / "documentation"
    if not documentation.is_dir():
        return []
    pages = [
        path for path in sorted(documentation.rglob("*.md")) if path.resolve() not in translated
    ]
    llms_txt = documentation / "llms.txt"
    if llms_txt.is_file():
        pages.append(llms_txt)
    return pages


def _relative(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _check_file(repo_root: Path, path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    relative = _relative(repo_root, path)
    lines = text.split("\n")
    failures = []
    for span in parse_spans(text):
        expected = _masked(expected_content(repo_root, span), span.options)
        actual = _masked(_actual_content(lines, span), span.options)
        if expected != actual:
            failures.append(
                f"{relative}:{span.open_line + 1}: snippet block for '{_source_label(span)}' "
                f"has drifted from its source — run 'poe snippet-sync' to update the page, or "
                f"fix '{span.source_path}' if the page was right"
            )
    return failures


def check_repository(repo_root: Path) -> list[str]:
    """Every drifted snippet block across every English documentation page, in file/line order,
    plus a stale `documentation/llms.txt` docs-vs-published banner line (`scripts/llms_banner.py`).
    """
    failures: list[str] = []
    for path in _english_markdown_files(repo_root):
        failures.extend(_check_file(repo_root, path))
    failures.extend(check_banner(repo_root))
    return failures


def _sync_file(repo_root: Path, path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    relative = _relative(repo_root, path)
    changed: list[str] = []
    for span in reversed(parse_spans(text)):  # back to front: earlier offsets stay valid
        expected = expected_content(repo_root, span)
        if _actual_content(lines, span) != expected:
            lines[span.content_start : span.content_end] = expected.split("\n")
            changed.append(
                f"{relative}:{span.open_line + 1}: resynced from '{_source_label(span)}'"
            )
    if changed:
        path.write_text("\n".join(lines), encoding="utf-8")
    return list(reversed(changed))  # report in document order


def sync_repository(repo_root: Path) -> list[str]:
    """Rewrites every drifted snippet block in place, English pages only. Returns what changed."""
    changes: list[str] = []
    for path in _english_markdown_files(repo_root):
        changes.extend(_sync_file(repo_root, path))
    return changes


def main() -> int:
    failures = check_repository(REPO_ROOT)
    if failures:
        print("ERROR: snippet-check found page content out of sync with its source:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("snippet-check: every embedded code/output block matches its source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
