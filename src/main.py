import os
from writing_agent import WritingAgent

def run():
    product = os.getenv("PROMPT", "AI productivity tool")
    agent = WritingAgent()
    return agent.write_landing_page(product)

if __name__ == "__main__":
    print(run())
