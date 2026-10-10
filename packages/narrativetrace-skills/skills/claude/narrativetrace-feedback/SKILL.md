---
name: narrativetrace-feedback
description: "Reports a defect in NarrativeTrace itself -- the library, the doctor, an agent skill, or the published install prompt. Use when a doctor finding is wrong or its fix does not work, when a skill step cannot be followed or its verify cannot be met, when the install prompt is wrong, or when the library misbehaves and the project is configured correctly. Drafts the report from this project (the install coordinates, the doctor's own JSON report, and at most one structural trace), refuses to write one that carries a value from your traces and names the rule that refused it, shows you the whole draft, and then asks once whether to file it publicly. Files nothing without your answer and sends nothing anywhere. Say 'report this to NarrativeTrace', 'the doctor's fix did not work', or 'file a bug about this skill' to invoke it."
when_to_use: "Non-obvious triggers: a doctor fix that leaves the same finding failing; a skill step whose verify cannot be met on a correctly configured project; wording in the install prompt that led somewhere wrong."
---

# narrativetrace-feedback

## 1. Gather what the report needs

```bash
uv run narrativetrace doctor || true
```

**verify:** `uv run narrativetrace doctor --json | uv run python -c 'import json, sys
report = json.load(sys.stdin)
findings = report.get("findings")
sys.exit(1 if not isinstance(findings, list) or len(findings) != 19 else 0)
'`

**failure:** the CLI is not found, or the project has no pyproject.toml — NarrativeTrace is not installed in this project's environment. Fix: report under the prompt or library category instead -- those do not need a doctor report

## 2. Draft the report and let the gate check it

```bash
uv run narrativetrace feedback draft --category <category> --step "<where it happened>" --did "<what you did>" --happened "<what happened>" --expected "<what you expected>"
```

**verify:** `uv run python -c 'import pathlib, sys
root = pathlib.Path("build/narrativetrace/feedback")
paths = [root / (stem + ".md") for stem in ("feedback-draft", "feedback-body")]
sys.exit(0 if all(p.is_file() and p.stat().st_size for p in paths) else 1)
'`

**failure:** the command exits 2 naming a vf.* rule — a field carries a value from this project's own run -- a rendered call line, an elapsed time, a credential-shaped string, an address. Fix: rewrite that one field to describe what happened instead of pasting it, and draft again; never work around the rule by moving the text to another field

## 3. Show the whole draft, not a summary of it

```bash
uv run python -c 'import pathlib
draft = pathlib.Path("build/narrativetrace/feedback") / ("feedback-draft" + ".md")
print(draft.read_text(encoding="utf-8"))
'
```

## 4. Ask once whether to file it, then stop the turn

## 5. Print the way to file it, and nothing else

```bash
uv run narrativetrace feedback url --category <category> --step "<where it happened>" --did "<what you did>" --happened "<what happened>" --expected "<what you expected>"
```

**verify:** `uv run narrativetrace feedback url --category <category> --step "<where it happened>" --did "<what you did>" --happened "<what happened>" --expected "<what you expected>" | uv run python -c 'import sys
sys.exit(0 if "/issues/new?template=" in sys.stdin.read() else 1)
'`

## Always

- Show the whole draft before asking anything. (filing is public and permanent, and a person can only approve what they have actually read)
- End the turn on the question, with nothing after it. (the answer is the user's next message, never something assumed in this one. Do not print the issue URL or run gh before the user says yes — showing the URL is the filing.)
- Ask in the user's own language. (the report may be written in any language, and a question nobody understands is not a question)
- Tell the user that filing is public, under their own account, before they answer. (a public issue shows that their project uses NarrativeTrace, and that is their decision to make knowingly)
- With the printed URL, name the file to paste and where. (the URL carries the short fields only; the body is never in it, so the user must paste the body file the verb names into the form's last box)

## Never

- Never attach a rendered trace, a log file or a source file. (those carry the values from the user's own run; the structural trace carries the same shape of the same call without any of them, and the verb attaches it on its own)
- Never file in the turn that asked. (approval is the user's next message -- a yes assumed in the same turn is not one)
- Never edit the draft after showing it. (what was approved has to be what is filed, so a changed report is drafted again and shown again)
- Never open the URL or run the printed command. (submitting is the user's act, in their own browser or their own shell, under their own account)
- Never route a rule's refusal around the gate. (a field that cannot be filed is a field to rewrite, not to move somewhere the rule does not look)
