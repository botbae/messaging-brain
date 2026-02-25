from dataclasses import dataclass
from typing import Optional


@dataclass
class ClientBrief:
    product: str
    audience: str
    pain: str
    offer: str
    tone: str
    cta: str
    examples: Optional[str] = ""
    context: Optional[str] = ""


def clean_sentence(s: str) -> str:
    text = " ".join((s or "").split()).strip()
    if not text:
        return ""
    if text[-1] not in ".!?":
        text += "."
    return text


def clean_phrase(s: str) -> str:
    text = " ".join((s or "").split()).strip()
    if not text:
        return ""
    for sep in [".", "!", "?"]:
        parts = [p.strip() for p in text.split(sep) if p.strip()]
        if parts:
            text = parts[0]
            break
    if text and text[-1] in ".!?":
        text = text[:-1]
    return text


def lower_first(s: str) -> str:
    if not s:
        return ""
    first, rest = s[0], s[1:]
    if "A" <= first <= "Z":
        first = first.lower()
    return first + rest


@dataclass
class WritingAgent:
    name: str = "WritingAgent"

    def write_landing_page(self, brief: ClientBrief) -> str:
        audience_raw = brief.audience or "your ideal customers"
        pain_raw = brief.pain or "struggling to understand the real value you provide"
        offer_raw = brief.offer or "a clear, conversion-focused narrative around your product"
        tone_raw = brief.tone or "clear, confident, and human"
        cta_raw = brief.cta or "Book a short call to sharpen your product story."

        audience_phrase = clean_phrase(audience_raw) or "your ideal customers"
        pain_sentence = clean_sentence(pain_raw)
        offer_phrase = clean_phrase(offer_raw) or "a clear, conversion-focused narrative around your product"
        tone_phrase = clean_phrase(tone_raw) or "clear, confident, and human"
        tone_phrase = lower_first(tone_phrase)
        offer_phrase = lower_first(offer_phrase)
        cta_sentence = clean_sentence(cta_raw)

        examples_section = ""
        if brief.examples:
            examples_section = f"""
EXAMPLES / INSPIRATION
{brief.examples}
""".rstrip()

        extra_context_section = ""
        if brief.context:
            extra_context_section = f"""
ADDITIONAL CONTEXT
{brief.context}
""".rstrip()

        body = f"""
HEADLINE
{brief.product}: messaging that actually converts

SUBHEAD
For {audience_phrase}. {pain_sentence} This positions you with {offer_phrase} in a {tone_phrase} voice.

PROBLEM
Right now, your product sounds just like every other tool. Visitors skim, get confused, and bounce before they feel why it matters.

SOLUTION
We turn your brief into sharp, specific language that shows the problem, the outcome, and why your product is the obvious choice.

CORE PROMISE
If a smart, distracted visitor only reads this page once, they will still remember what you do and why it is worth trying.

KEY SECTIONS
1. Hero: one clear promise tied to the main pain.
2. Social proof: logos, short quotes, and a simple metric if you have it.
3. Product tour: 3–5 moments that show how life feels with your product.
4. Objections: \"What if this is too complex / risky / expensive?\" answered in plain language.
5. Final CTA: one simple next step.

TONE & VOICE
Write in a {tone_phrase} tone. Prefer concrete examples over buzzwords. Fewer adjectives, more specifics.

CALL TO ACTION
{cta_sentence}
""".rstrip()

        if examples_section:
            body = f"{body}\n\n{examples_section}"

        if extra_context_section:
            body = f"{body}\n\n{extra_context_section}"

        return body + "\n"

    def rewrite_landing_page(self, brief: ClientBrief, draft: str, critique: dict) -> str:
        """Deterministic rewrite pass based on critic feedback.

        This is intentionally rule-based (no LLM) so the system remains free and predictable.
        """
        # Rebuild key sections with slightly stronger specificity.
        product = clean_phrase(brief.product) or "Your product"
        audience = clean_phrase(brief.audience) or "your ideal customers"
        pain = clean_sentence(brief.pain or "Visitors do not quickly understand why your product matters")

        offer_phrase = lower_first(clean_phrase(brief.offer) or "a clear, conversion-focused narrative around your product")
        tone_phrase = lower_first(clean_phrase(brief.tone) or "clear, confident, and human")
        cta = clean_sentence(brief.cta or "Book a short call to sharpen your product story")

        # If the critic detected generic headline, make headline more concrete using the offer.
        headline = f"{product}: {offer_phrase}" if critique.get("flags", {}).get("generic_headline") else f"{product}: messaging that actually converts"

        # If the critic thinks CTA is weak, harden it with a more specific action.
        if critique.get("flags", {}).get("weak_cta"):
            cta = clean_sentence(brief.cta or "Get a 15-minute messaging teardown")

        # If the critic thinks the problem is generic, tie it to the user-provided pain.
        problem = (
            f"Right now, your page does not make the value obvious for {audience}. {pain} "
            "So visitors skim, feel uncertain, and bounce."
        )

        solution = (
            "We turn your brief into sharp, specific language that shows the problem, the outcome, "
            "and why your product is the obvious next step."
        )

        subhead = (
            f"For {audience}. {pain} "
            f"This positions you with {offer_phrase} in a {tone_phrase} voice."
        )

        examples_section = ""
        if brief.examples:
            examples_section = f"""
EXAMPLES / INSPIRATION
{brief.examples}
""".rstrip()

        extra_context_section = ""
        if brief.context:
            extra_context_section = f"""
ADDITIONAL CONTEXT
{brief.context}
""".rstrip()

        # Critique section (optional): include only if requested by the caller.
        critique_block = ""
        if critique.get("include_in_output"):
            critique_block = f"""
CRITIQUE (AUTO)
Score: {critique.get('score', 'NA')}/10
""".rstrip()
            notes = critique.get("notes", [])
            if notes:
                critique_block += "\n" + "\n".join([f"- {n}" for n in notes])

        body_v2 = f"""
HEADLINE
{headline}

SUBHEAD
{subhead}

PROBLEM
{problem}

SOLUTION
{solution}

CORE PROMISE
If a smart, distracted visitor only reads this page once, they will still remember what you do and why it is worth trying.

KEY SECTIONS
1. Hero: one clear promise tied to the main pain.
2. Social proof: logos, short quotes, and a simple metric if you have it.
3. Product tour: 3–5 moments that show how life feels with your product.
4. Objections: "What if this is too complex / risky / expensive?" answered in plain language.
5. Final CTA: one simple next step.

TONE & VOICE
Write in a {tone_phrase} tone. Prefer concrete examples over buzzwords. Fewer adjectives, more specifics.

CALL TO ACTION
{cta}
""".rstrip()

        # Append optional blocks
        blocks = [body_v2]
        if critique_block:
            blocks.append(critique_block)
        if examples_section:
            blocks.append(examples_section)
        if extra_context_section:
            blocks.append(extra_context_section)

        return "\n\n".join(blocks) + "\n"

    def write_linkedin_post(self, brief: ClientBrief) -> str:
        product = clean_phrase(brief.product) or "Your product"
        audience_phrase = clean_phrase(brief.audience) or "your ideal customers"
        pain_sentence = clean_sentence(
            brief.pain or "Most teams struggle to explain their product in a single, clear scroll."
        )
        offer_phrase = lower_first(
            clean_phrase(brief.offer) or "clear, high-conversion messaging"
        )
        tone_phrase = lower_first(clean_phrase(brief.tone) or "clear, confident, and human")
        cta = clean_sentence(
            brief.cta
            or "If you want a teardown of your current page, comment 'TEARDOWN' or send a quick DM."
        )

        hook = (
            f"{product} does not need more features. "
            f"It needs clearer words for {audience_phrase}."
        )

        problem = (
            f"{pain_sentence} Right now, visitors skim your page, nod along, and still do not feel "
            "the moment when your product actually helps them."
        )

        insight = (
            "The pages that convert are not the ones with the most sections. "
            f"They are the ones that name a sharp problem, show a concrete outcome, "
            f"and speak in a {tone_phrase} voice instead of generic SaaS jargon."
        )

        soft_pitch = (
            f"If you want, I can help you with {offer_phrase} "
            f"so {audience_phrase} understand it on the first read."
        )

        body = f"""
HOOK
{hook}

PROBLEM
{problem}

INSIGHT
{insight}

SOFT PITCH
{soft_pitch}

CTA
{cta}
""".rstrip()

        return body + "\n"


@dataclass
class CriticAgent:
    name: str = "CriticAgent"

    def review_landing_page(self, draft: str, brief: ClientBrief) -> dict:
        """Rule-based critique for writing quality and conversion clarity."""
        text = (draft or "").strip()

        flags = {
            "generic_headline": False,
            "weak_cta": False,
            "missing_audience": False,
            "missing_pain": False,
        }
        notes: list[str] = []

        # Heuristics
        generic_phrases = [
            "messaging that actually converts",
            "just like every other tool",
            "sharp, specific language",
        ]

        # Headline quality
        if "HEADLINE" in text and any(p in text for p in generic_phrases):
            flags["generic_headline"] = True
            notes.append("Headline feels generic. Prefer a concrete outcome or your specific offer.")

        # Audience presence
        audience = clean_phrase(brief.audience)
        if audience and audience.lower() not in text.lower():
            flags["missing_audience"] = True
            notes.append("Audience is not explicit enough. Name who this is for in the hero.")

        # Pain presence
        pain = clean_phrase(brief.pain)
        if pain and pain.lower()[:25] not in text.lower():
            flags["missing_pain"] = True
            notes.append("Pain is not specific. Tie the hero and problem section to the provided pain.")

        # CTA strength
        cta = clean_phrase(brief.cta)
        if cta:
            weak_words = ["start", "learn", "explore", "see", "discover"]
            if any(w in cta.lower().split()[:2] for w in weak_words):
                flags["weak_cta"] = True
                notes.append("CTA is soft. Use a concrete action: 'Get a teardown', 'Book a working session', etc.")

        # Score: start at 10 and subtract for flags
        score = 10
        score -= 2 if flags["generic_headline"] else 0
        score -= 2 if flags["missing_audience"] else 0
        score -= 2 if flags["missing_pain"] else 0
        score -= 1 if flags["weak_cta"] else 0
        score = max(1, score)

        return {
            "score": score,
            "flags": flags,
            "notes": notes,
            # main.py can toggle this to include critique in output
            "include_in_output": False,
        }
