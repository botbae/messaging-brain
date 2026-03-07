# Failures

Bugs, prompt failures, and wrong assumptions that were fixed and are worth remembering.

The goal is not to log every fix — it is to capture non-obvious failures that could recur without this record.

---

## When to add an entry

- A bug was fixed that could be reintroduced by a future change
- A prompt pattern reliably produced bad output before it was corrected
- A validation assumption turned out to be wrong in practice
- An architectural decision caused an unexpected failure mode

## When NOT to add an entry

- Trivial typos or obvious syntax errors
- One-off environment issues (Ollama not running, missing .env)
- Failures that are already prevented by code-level guards

---

## Format

Filename: `YYYY-MM-DD-short-description.md`

```markdown
# [Short title of the failure]

**Date:** YYYY-MM-DD
**Affected:** [file or component]

## What happened
[One or two sentences: what the symptom was]

## Root cause
[What the actual problem was]

## Fix
[What was changed to resolve it]

## Watch for
[What pattern or change could reintroduce this]
```

---

## Entries

- `2026-03-07-ux-pack-decisions-not-injected.md` — Brain decisions loaded but not passed to UX pack LLM prompt
