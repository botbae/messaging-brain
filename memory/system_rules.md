# System Rules

Core rules of the Unimind writing/positioning system. AI tools can read this file for context.

---

## Landing Page Rules

- Must use headers in this order:
  - **HEADLINE**
  - **SUBHEAD**
  - **WHO ITS FOR**
  - **PROBLEM**
  - **WHY CURRENT OPTIONS FAIL**
  - **WHAT THIS IS**
  - **DIFFERENTIATION**
  - **PROOF / SIGNALS**
  - **CTA**

---

## LinkedIn Post Rules

- Headers: **HOOK**, **PROBLEM**, **INSIGHT**, **SOFT PITCH**, **CTA**
- Hooks cannot be generic
- CTA must be one line

---

## UX Pack Rules

Headers (in order):

- **UX CONTEXT**
- **ONBOARDING**
- **EMPTY STATE**
- **ERROR**
- **TOAST**
- **BUTTON LABELS**

Product UX must **never** reference:

- brief.json
- CLI commands
- generation modes
- operator workflows

---

## Architecture Layers

1. **Brief intake** — Load or prompt for product, audience, pain, offer, tone, CTA, context
2. **Decision extraction** — Extract positioning decisions (ICP, problem, alternatives, outcome, category, differentiation)
3. **Generation layer** — Landing, LinkedIn, UX pack, positioning, etc.
4. **Validation layer** — Structure checks, banned phrases, scenario tags (product vs operator)
5. **Output save** — Versioned and latest files, manifest log

---

## Source of Truth Rules

- `clients/<client>/product_profile.json` is the **source of truth** for all content generation when a client session is active.
- When `product_profile.json` exists, generators use `agent.brain_decisions` and skip the decision-extraction LLM call.
- Brief fields (`brief.audience`, `brief.pain`, etc.) are used only for fallbacks and fact-grounding — never as the primary source for generation prompts when the brain is loaded.
- Each generator method is responsible for explicitly injecting the relevant decision fields (`icp`, `primary_problem`, `desired_outcome`, etc.) into its LLM prompt. Calling `extract_positioning_decisions()` is not sufficient — the returned dict must be used in the prompt strings.
