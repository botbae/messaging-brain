# System Brain

This folder is the **System Brain** for Unimind — engineering memory about the system itself.
It is intentionally flat, markdown-only, and human-readable. No embeddings, no vector DB, no external dependencies.

---

## System Brain vs Product Brain

| | System Brain | Product Brain |
|---|---|---|
| **What it stores** | Engineering context about Unimind | Messaging intelligence for a specific product |
| **Lives in** | `memory/` and `docs/` | `clients/<client>/` |
| **Examples** | Architecture rules, bugs, module states | brief.json, product_profile.json, outputs |
| **Who reads it** | Engineers, AI tools working on Unimind | Generators, agents running for a client |

---

## Folder structure

```
memory/
  README.md            — this file; System Brain index
  system_rules.md      — generation rules (headers, banned phrases, validation)
  evolution/           — milestone entries: what changed and why
  failures/            — bugs and prompt failures worth remembering
  decisions/           — architectural choices with tradeoffs
  modules/             — module state notes (active, parked, experimental)
```

---

## Folder purposes

### system_rules.md
Rules that govern all content generation: output headers, banned phrases, validation counts, source-of-truth conventions. AI tools read this to stay aligned. Edit it when a rule changes in code and the old rule would mislead future reasoning.

### evolution/
One markdown file per architectural milestone (e.g. `2026-03-07-brain-pipeline.md`). Captures: what problem was solved, what was introduced, before/after summary. Not a commit log — only write entries for changes that shift how the system works.

### failures/
Bugs, prompt failures, and wrong assumptions that were fixed and are worth remembering. The goal is to avoid repeating the same mistake. Write an entry when a non-obvious bug is fixed or when a prompt pattern reliably produces bad output.

### decisions/
Architectural choices that had real tradeoffs and might be revisited. Each entry states: what was decided, why, alternatives considered, when to reconsider. Do not log every trivial choice — only decisions that a future engineer or AI might reasonably question.

### modules/
Brief state notes for modules that are parked, experimental, or have known activation requirements. For the detailed module list, see `docs/parked_modules.md`. This folder is for per-module notes that don't fit the parked_modules format.

---

## Write rules

**Add to System Brain when:**
- An architectural decision was made with real tradeoffs
- A non-obvious bug was fixed that could recur
- A module's status changed (activated, deprecated, parked)
- A significant milestone shifted how the system works

**Do NOT add:**
- Random terminal output or debug logs
- Every code change (use git history for that)
- Output artifacts from generation runs
- Temporary notes or in-progress work
- Anything that duplicates what's already in the README, docs/ or the code docstrings
