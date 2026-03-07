# Modules

Brief status notes for modules that are parked, experimental, or have known activation requirements.

For the full module list with activation instructions, see `docs/parked_modules.md`.

This folder is for notes that go beyond a simple active/parked status — for example, if a module was activated and then re-parked, or if a module has a known interaction with another component worth recording.

---

## When to add an entry here (vs. just updating parked_modules.md)

Use `docs/parked_modules.md` for:
- Listing all non-active modules with one-paragraph summaries
- Activation instructions

Use this folder for:
- Notes about a module that changed state (was parked, then activated, then re-parked)
- Known interactions or coupling between two modules
- A module that was removed entirely (tombstone note)

---

## Format

Filename: `YYYY-MM-DD-module-name.md` for a state change, or just `module-name.md` for a standing note.

```markdown
# [Module name]

**File:** `src/path/to/module.py`
**Status:** active | parked | removed
**As of:** YYYY-MM-DD

## Note
[What changed or what is worth knowing that isn't in parked_modules.md]
```

---

## Current module states (summary)

For full details see `docs/parked_modules.md`.

| Module | Status | Location |
|---|---|---|
| WritingAgent | active | `src/agents/writing_agent.py` |
| CriticAgent | active | `src/agents/writing_agent.py` |
| StrategistAgent | active | `src/agents/writing_agent.py` |
| FactGuardAgent | active | `src/agents/writing_agent.py` |
| GroundingAgent | active | `src/agents/writing_agent.py` |
| ProductProfile | active | `src/product_profile.py` |
| OllamaProvider | active | `src/core/model_provider.py` |
| CloudProviderStub | parked | `src/core/model_provider.py` |
| write_ux_microcopy() | legacy | `src/agents/writing_agent.py` |
| AGENT_LOOP (ux modes) | parked | `src/main.py` + `src/agent_loop.py` |
| memory auto-injection | not started | — |
| CTA consistency checker | not started | — |
