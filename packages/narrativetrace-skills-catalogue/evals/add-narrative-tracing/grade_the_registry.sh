#!/bin/sh
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
# World-state verifier for a REGISTRY case: what the registry left in the project, and what the
# installer then does with it. Shared by both registry cases; run with cwd set to the scaffolded
# fixture copy, from a case's graders/verify.sh, with $1 naming the registry that delivered the
# pages (claude-marketplace | npx-skills) and $2 the service boundary that fixture defines.
#
# The published prompt's own promises are NOT graded here -- grade_the_prompt.sh is the whole of
# that, and it runs last. What is graded here is the three things only a registry case can be
# asked, in the order that fails cheapest first:
#
#   1. No vendor page was written THROUGH a symbolic link. `npx skills add` makes
#      .claude/skills/<name> a link to .agents/skills/<name>, so writing the vendor flavour through
#      it would destroy the open-standard page it had just adopted. The invariant is keyed on the
#      lines the two flavours differ by: `allowed-tools` and `when_to_use` are in the vendor page
#      and in no other. A page may lack ONE of them -- the reporting skill declares no
#      `allowed-tools` by design -- so the vendor flavour is "either line", never "this line".
#   2. The installer refuses nothing, so no `--force` was needed. A registry's pages are our own
#      rendered pages, so an identical one is adopted rather than refused -- and the refusal a
#      pre-adoption installer produced is exactly what a reader would have reached for --force over.
#   3. The registry's own files are still the registry's: its lock file, and the pages it wrote
#      where our installer never looks.
#
# $NARRATIVETRACE_CLI_PROJECT is where the installer THIS CHECKOUT provides lives; run.py tells the
# grader and nobody else. Check 2 has to read that installer rather than the one the project
# resolved from PyPI, because the published release predates the adoption and symlink safety the
# check is about (design D8: what a reader runs against the public repository waits for this port's
# own carrier release). The agent's own step 3 meanwhile runs whatever the project resolved, which
# is what a reader has today -- so a pre-adoption refusal there is a release state, graded by
# grade_the_prompt.sh's step-3 gate, and never mistaken for this check.
set -e

registry="$1"
service="$2"
if [ -z "$registry" ] || [ -z "$service" ]; then
  echo "usage: grade_the_registry.sh <claude-marketplace|npx-skills> <TracedServiceName>" >&2
  exit 1
fi
case "$registry" in
  claude-marketplace | npx-skills) ;;
  *)
    echo "unknown registry \"$registry\" -- the graders know claude-marketplace and npx-skills" >&2
    exit 1
    ;;
esac
here=$(dirname "$0")

# ------------------------------------------------------------------------------------------------
# 1. Nothing was written through a link.
# ------------------------------------------------------------------------------------------------
for page in .agents/skills/*/SKILL.md; do
  [ -f "$page" ] || continue
  if grep -qE "^(allowed-tools|when_to_use):" "$page"; then
    echo "$page carries the VENDOR flavour's frontmatter -- the open-standard page was" >&2
    echo "overwritten, which is what writing through .claude/skills's symbolic link does" >&2
    exit 1
  fi
done

for entry in .claude/skills/*; do
  [ -e "$entry" ] || [ -L "$entry" ] || continue
  if [ -L "$entry" ]; then
    target=$(readlink "$entry")
    case "$target" in
      *.agents/skills/*)
        echo "no write-through: $entry is still the registry's link to $target" ;;
      *)
        echo "$entry is a symbolic link to $target, which is not the open-standard page the" >&2
        echo "registry pointed it at -- something replaced a link the installer must refuse" >&2
        exit 1 ;;
    esac
  elif ! grep -qE "^(allowed-tools|when_to_use):" "$entry/SKILL.md"; then
    echo "$entry/SKILL.md is a real page in the vendor's own directory but carries none of" >&2
    echo "the vendor-only frontmatter lines -- the wrong flavour was installed there" >&2
    exit 1
  else
    echo "no write-through: $entry holds the vendor flavour, as a real directory of its own"
  fi
done

# ------------------------------------------------------------------------------------------------
# 2. The installer refuses nothing on the tree the registry made, and needs no --force.
#    A dry run writes nothing and always exits 0, so the PLAN itself is what is read.
# ------------------------------------------------------------------------------------------------
if [ -z "$NARRATIVETRACE_CLI_PROJECT" ]; then
  echo "NARRATIVETRACE_CLI_PROJECT is unset -- run.py sets it for every grader, and without it" >&2
  echo "the adoption proof would silently read the PUBLISHED installer instead of this one" >&2
  exit 1
fi

plan=$(uv run --frozen --project "$NARRATIVETRACE_CLI_PROJECT" narrativetrace init \
  --dry-run --json) || {
  echo "this checkout's installer could not produce a plan for the registry-installed tree" >&2
  exit 1
}

echo "$plan" | uv run --frozen --project "$NARRATIVETRACE_CLI_PROJECT" python -c '
import json, sys
plan = json.load(sys.stdin)
actions = plan.get("actions", [])
refused = [a for a in actions if a.get("status") == "refused"]
if refused:
    print("the installer refuses actions on the registry-installed tree, so a reader would reach",
          "for --force:", refused, file=sys.stderr)
    sys.exit(1)
# An EMPTY plan is a pass, deliberately: on a tree where the install was already applied and is
# current there is nothing left to plan, and that is the one state "refuses nothing" should most
# obviously accept. A non-emptiness guard here failed the applied branch of the npx case in
# rehearsal, which is what rehearsal is for.
print("no refusals: the plan is", ", ".join(sorted({a["kind"] for a in actions})) or "empty")
'

# ------------------------------------------------------------------------------------------------
# 3. What this particular registry leaves behind, and what the installer may never touch of it.
# ------------------------------------------------------------------------------------------------
case "$registry" in
  npx-skills)
    test -f skills-lock.json || {
      echo "the registry tool's own lock file is gone -- the installer may remove only what it" >&2
      echo "wrote itself" >&2
      exit 1
    }
    uv run --frozen --project "$NARRATIVETRACE_CLI_PROJECT" python - <<'PY'
import json, pathlib, sys
lock = json.loads(pathlib.Path("skills-lock.json").read_text())
names = sorted(lock.get("skills", {}))
if not names:
    print("skills-lock.json names no skill at all: the registry installed nothing", file=sys.stderr)
    sys.exit(1)
missing = [n for n in names if not pathlib.Path(".agents/skills", n, "SKILL.md").is_file()]
if missing:
    print("the lock file names skills with no page left on disk:", missing, file=sys.stderr)
    sys.exit(1)
# The vendor side the tool symlinked has to be there too -- as the link it made, or as the real
# directory the installer replaced it with. Gone means somebody removed what the registry left.
vendorless = [n for n in names if not pathlib.Path(".claude/skills", n).exists()
              and not pathlib.Path(".claude/skills", n).is_symlink()]
if vendorless:
    print("the registry pointed .claude/skills at these and now nothing is there:", vendorless,
          file=sys.stderr)
    sys.exit(1)
print("the registry's", len(names), "pages and its lock file are intact:", ", ".join(names))
PY
    # A third place this tool has been seen to write: real pages under agent/skills, with their
    # frontmatter reflowed by the tool itself. Our installer never looks there, so it must never
    # have stamped one. (skills@1.7.1, verified 2026-10-07, writes no such copy -- the loop is
    # empty then, and stays honest if a later version brings it back.)
    for page in agent/skills/*/SKILL.md; do
      [ -f "$page" ] || continue
      if grep -q "installed by narrativetrace init from" "$page"; then
        echo "$page carries our provenance line, but it is the registry tool's own copy in a" >&2
        echo "directory the installer does not own" >&2
        exit 1
      fi
    done
    ;;
  claude-marketplace)
    test ! -f skills-lock.json || {
      echo "a user-scope plugin install writes no lock file into the project, so this tree was" >&2
      echo "not made by the registry this case names" >&2
      exit 1
    }
    # User scope: the plugin's pages live in the agent's own configuration, never in the project.
    # So every page that IS in the project has to be one the installer wrote and stamped.
    for page in .agents/skills/*/SKILL.md .claude/skills/*/SKILL.md; do
      [ -f "$page" ] || continue
      grep -q "installed by narrativetrace init from" "$page" || {
        echo "$page is in the project without the installer's provenance line, and a user-scope" >&2
        echo "plugin install puts nothing in the project -- where did it come from?" >&2
        exit 1
      }
    done
    echo "user scope: the project carries no page the installer did not write"
    ;;
esac

# ------------------------------------------------------------------------------------------------
# 4. Everything the published prompt itself promises, graded exactly as the other cases grade it.
# ------------------------------------------------------------------------------------------------
sh "$here/grade_the_prompt.sh" "$service" "$registry"
