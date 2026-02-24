from dataclasses import dataclass

@dataclass
class WritingAgent:
    name: str = "WritingAgent"

    def analyze(self, product: str):
        return {
            "audience": "Founders and product builders",
            "problem": "They struggle to communicate product value clearly.",
            "promise": "Clear positioning and high-conversion messaging."
        }

    def write_landing_page(self, product: str):
        context = self.analyze(product)

        return f"""
HEADLINE
Build Better Messaging for {product}

SUBHEAD
Helping {context['audience']} explain their product clearly and convert users faster.

PROBLEM
{context['problem']}

SOLUTION
Our writing operator helps teams craft positioning, UX copy,
and marketing messaging that actually connects.

FEATURES
• Landing page copy
• Product positioning
• UX microcopy
• Marketing messaging

CTA
Start improving your messaging today.
"""
