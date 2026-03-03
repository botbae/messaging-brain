# Prompts: Decisions → expression and banned phrases

## Decisions → expression pattern

All client-facing content (landing, LinkedIn, UX pack) is generated in two steps:

1. **Decision phase**  
   `WritingAgent.extract_positioning_decisions(brief)` calls the LLM once to produce a **strict JSON** of positioning decisions:
   - `icp` — who it’s for  
   - `primary_problem` — core pain  
   - `current_alternative` — what they use today  
   - `desired_outcome` — what we want them to get to  
   - `category_frame` — how we category the product  
   - `differentiation` — how we’re different  
   - `anti_positioning` — what we’re not  

   No marketing tone, no storytelling, no hype. If the LLM returns invalid JSON or banned words, we retry once with a stricter prompt, then fall back to a brief-derived dict.

2. **Expression phase**  
   Each mode (landing, LinkedIn, UX pack) receives **only** this decisions dict plus `brief.tone` (as “user custom instructions”). Raw brief fields (product, audience, pain, offer, cta, examples, context) are **not** passed into the content prompt—they’re already encoded in the decisions. That keeps copy anchored to one strategy and avoids re-introducing vague or hype-heavy language.

## Banned phrases and why

These (and variants) are forbidden in generated copy so output stays concrete and non-generic:

| Phrase / family | Why banned |
|-----------------|------------|
| streamline, empower, unlock, transform | Vague “we make things better” without saying how. |
| innovative, cutting-edge, game-changing, best-in-class, revolutionize | Hype; doesn’t differentiate. |
| compelling message, drives results | Empty marketing filler. |
| you're not alone, ready to…, Let us… | Soft openers / CTAs that dilute a single clear ask. |
| Struggling to… (as hook) | Overused hook; we want a concrete observation. |
| killer app, you know the drill, meh | Colloquial filler. |
| high-quality, designed for, like you | Generic SaaS clichés. |

Landing has additional rules: **no questions in the HEADLINE**; LinkedIn **HOOK** must be a concrete observation and **CTA** must be one line only.

## Where this is enforced

- **Decision phase:** `extract_positioning_decisions` validates JSON and rejects output containing the decision-phase banned list; retry and fallback use the same list.
- **Landing / LinkedIn / UX pack:** Each generator has its own banned list and optional retry with a stricter system prompt. If the final text still fails validation, we fall back to a rule-based template built from the decisions (and brief for fallback only).
