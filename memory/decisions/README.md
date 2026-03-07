# Decisions

Architectural choices that had real tradeoffs and might be revisited later.

Not a log of every change. Only choices where the alternative was reasonable and the reasoning is worth preserving.

---

## When to add an entry

- A technology or approach was chosen over a plausible alternative
- A constraint was deliberately accepted (e.g. no external deps, no cloud calls)
- A design choice might look wrong to a future engineer without context
- A decision is likely to be revisited when the system scales

## When NOT to add an entry

- Obvious or trivial choices (e.g. "used a list instead of a set")
- Decisions that are already fully explained in code comments or docstrings
- Implementation details that don't affect system architecture

---

## Format

Filename: `YYYY-MM-DD-short-topic.md`

```markdown
# [Decision topic]

**Date:** YYYY-MM-DD
**Status:** active | superseded | under review

## Decision
[What was decided, in one or two sentences]

## Why
[The reasoning: what problem it solves, what constraint it satisfies]

## Alternatives considered
[What else was plausible and why it was not chosen]

## When to reconsider
[Conditions under which this decision should be revisited]
```

---

## Entries

- `2026-03-07-memory-is-markdown-only.md` — No vector DB; memory is plain markdown files
- `2026-03-07-ollama-local-default-cloud-stub.md` — Local Ollama as default; cloud provider stubbed out
