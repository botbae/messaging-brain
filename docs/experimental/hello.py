import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

msg = client.messages.create(
    model="claude-3-5-sonnet-latest",
    max_tokens=200,
    messages=[{"role":"user","content":"Say 'setup works' and one short tip for a beginner building agents."}],
)
print(msg.content[0].text)
