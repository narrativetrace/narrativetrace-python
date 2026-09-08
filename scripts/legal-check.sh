#!/usr/bin/env bash
# SPDX-License-Identifier: BUSL-1.1
#
# Legal reference-copy consistency gate.
#
# Legal text in this repository follows the canonical copies held in the reference repository
# (see legal.properties) — this script is what "derives from" means in practice, not
# just a comment. Three checks, all gated by the same WARN/STRICT policy below:
#
#   (a) marker well-formedness: every `<!-- legal:<name>:begin/end -->` pair in
#       README.md, NOTICE and the translated root READMEs (LEAME.md, LEIAME.md,
#       自述文件.md) is balanced, correctly named (plain-words, trademark) and
#       never nested or dangling. Never hand-edit inside a marked region — this
#       is what would catch it going out of shape. (There is no legal:exclusion
#       region: an HTML comment inside a GFM table — as the exclusion clause
#       sits in some runtimes — terminates the table, and the exclusion sentence
#       already lives verbatim inside legal:plain-words, so a separate region
#       would only duplicate it. The exclusion paraphrase stays unmarked,
#       ordinary per-repo prose.)
#   (b) every packages/*/LICENSE is byte-identical to the root LICENSE — belt to
#       the existing pytest suspenders (packages/narrativetrace/tests/
#       test_distribution_licensing.py), cheap enough to run twice.
#   (c) when the reference repo (legal.referenceRepo) is present alongside this one:
#       the root LICENSE must equal the reference LICENSE with only the "Licensed
#       Work:" description swapped for legal.licensedWork, and each file's
#       legal:plain-words region must be byte-identical to the reference copy's
#       region in the same file (the paraphrase is shared prose, not
#       repo-specific — unlike the trademark sentence, which lives in per-repo
#       prose and is marked but not content-compared).
#
# Policy: WARN by default (poe check runs this every commit without blocking on
# drift someone hasn't gotten to yet); LEGAL_CHECK_STRICT=1 turns every finding
# into a failure (used by the (private) publish pipeline as a preflight — nothing ships public
# with unreviewed legal drift). The reference repo missing entirely (a Python-only
# checkout, no sibling clone) is not a finding — checks (a) and (b) still run,
# (c) is skipped with a note.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

STRICT="${LEGAL_CHECK_STRICT:-0}"
ISSUES=0

note() { echo ">> $*"; }
issue() {
    echo "WARN: $*" >&2
    ISSUES=$((ISSUES + 1))
}

prop() {
    sed -n "s/^$1=//p" "$REPO_ROOT/legal.properties" | head -1
}

# --------------------------------------------------------------------------- #
# (a) marker well-formedness                                                  #
# --------------------------------------------------------------------------- #
MARKER_FILES=(README.md NOTICE LEAME.md LEIAME.md 自述文件.md)

check_markers() {
    python3 - "$1" <<'PYEOF'
import re
import sys

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
tokens = re.findall(r"<!-- legal:([a-z-]+):(begin|end) -->", text)
valid = {"plain-words", "trademark"}
open_names = []
errors = []
for name, kind in tokens:
    if name not in valid:
        errors.append(f"unknown marker name '{name}'")
        continue
    if kind == "begin":
        if name in open_names:
            errors.append(f"'{name}' opened twice without a close in between")
        else:
            open_names.append(name)
    else:
        if name in open_names:
            open_names.remove(name)
        else:
            errors.append(f"'{name}' closed without a matching open")
for name in open_names:
    errors.append(f"'{name}' opened but never closed")
for error in errors:
    print(f"{path}: {error}")
sys.exit(1 if errors else 0)
PYEOF
}

any_markers_checked=0
for f in "${MARKER_FILES[@]}"; do
    [ -f "$REPO_ROOT/$f" ] || continue
    any_markers_checked=1
    if ! check_markers "$REPO_ROOT/$f"; then
        issue "marker well-formedness failed in $f (see above)"
    fi
done
[ "$any_markers_checked" = 1 ] && note "marker well-formedness checked: ${MARKER_FILES[*]}"

# --------------------------------------------------------------------------- #
# (b) packages/*/LICENSE byte-equal root LICENSE                              #
# --------------------------------------------------------------------------- #
ROOT_LICENSE="$REPO_ROOT/LICENSE"
if [ ! -f "$ROOT_LICENSE" ]; then
    issue "root LICENSE is missing"
else
    checked=0
    for lic in "$REPO_ROOT"/packages/*/LICENSE; do
        [ -f "$lic" ] || continue
        checked=$((checked + 1))
        if ! cmp -s "$ROOT_LICENSE" "$lic"; then
            issue "${lic#"$REPO_ROOT"/} is not byte-identical to root LICENSE"
        fi
    done
    note "packages/*/LICENSE byte-equality checked against root LICENSE ($checked distribution(s))."
fi

# --------------------------------------------------------------------------- #
# (c) reference-repo derived checks                                           #
# --------------------------------------------------------------------------- #
if [ ! -f "$REPO_ROOT/legal.properties" ]; then
    issue "legal.properties is missing — cannot locate the reference repo or the Licensed Work description"
else
    REFERENCE_REPO_REL="$(prop 'legal\.referenceRepo')"
    LICENSED_WORK="$(prop 'legal\.licensedWork')"
    REFERENCE_REPO="$REPO_ROOT/$REFERENCE_REPO_REL"

    if [ ! -d "$REFERENCE_REPO" ]; then
        note "reference repo not found at $REFERENCE_REPO_REL — skipping derived-LICENSE and per-language region compares."
    else
        if ! python3 - "$REPO_ROOT" "$REFERENCE_REPO" "$LICENSED_WORK" <<'PYEOF'
from __future__ import annotations

import re
import sys
from pathlib import Path

repo_root, reference_root, licensed_work = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
issues: list[str] = []


def region(text: str, name: str) -> str | None:
    match = re.search(
        rf"<!-- legal:{re.escape(name)}:begin -->\n(.*?)<!-- legal:{re.escape(name)}:end -->\n",
        text,
        re.DOTALL,
    )
    return match.group(1) if match else None


# --- derived LICENSE: reference LICENSE with the Licensed Work description swapped ---
reference_license_path = reference_root / "LICENSE"
our_license_path = repo_root / "LICENSE"
if not reference_license_path.is_file():
    issues.append(f"reference repo has no LICENSE at {reference_license_path}")
elif not our_license_path.is_file():
    issues.append("root LICENSE is missing")
else:
    reference_text = reference_license_path.read_text(encoding="utf-8")
    our_text = our_license_path.read_text(encoding="utf-8")
    pattern = re.compile(r"^(Licensed Work:\s+).*?( version \{\{VERSION\}\}\..*)$", re.MULTILINE)
    derived_text, count = pattern.subn(lambda m: m.group(1) + licensed_work + m.group(2), reference_text)
    if count != 1:
        issues.append("could not locate exactly one 'Licensed Work:' line in the reference LICENSE")
    elif derived_text != our_text:
        issues.append(
            "root LICENSE differs from the reference LICENSE beyond the Licensed Work description "
            "(derived text does not match byte-for-byte)"
        )

# --- per-language legal:plain-words region compares -------------------------------
for name in ("README.md", "LEAME.md", "LEIAME.md", "自述文件.md"):
    ours_path = repo_root / name
    reference_path = reference_root / name
    if not ours_path.is_file() or not reference_path.is_file():
        continue
    ours_region = region(ours_path.read_text(encoding="utf-8"), "plain-words")
    reference_region = region(reference_path.read_text(encoding="utf-8"), "plain-words")
    if ours_region is None or reference_region is None:
        continue
    if ours_region != reference_region:
        issues.append(f"{name}: legal:plain-words region differs from the reference copy")

for message in issues:
    print(message)
sys.exit(1 if issues else 0)
PYEOF
        then
            issue "reference-repo derived checks failed (see above)"
        else
            note "derived-LICENSE and per-language legal:plain-words regions match the reference repo."
        fi
    fi
fi

# --------------------------------------------------------------------------- #
# Verdict                                                                     #
# --------------------------------------------------------------------------- #
if [ "$ISSUES" -gt 0 ]; then
    if [ "$STRICT" = "1" ]; then
        echo "legal-check: $ISSUES issue(s) found, failing (LEGAL_CHECK_STRICT=1)." >&2
        exit 1
    fi
    echo "legal-check: $ISSUES issue(s) found (warn-only — set LEGAL_CHECK_STRICT=1 to fail on these)." >&2
    exit 0
fi
note "legal-check: clean."
