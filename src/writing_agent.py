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
